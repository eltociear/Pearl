from typing import Any, Dict, Iterable, Optional, Type

import torch
from pearl.api.action_space import ActionSpace
from pearl.neural_networks.common.value_networks import VanillaQValueNetwork
from pearl.neural_networks.sequential_decision_making.actor_networks import (
    ActorNetworkType,
    GaussianActorNetwork,
)
from pearl.neural_networks.sequential_decision_making.q_value_network import (
    QValueNetwork,
)
from pearl.policy_learners.exploration_modules.common.no_exploration import (
    NoExploration,
)
from pearl.policy_learners.exploration_modules.exploration_module import (
    ExplorationModule,
)
from pearl.policy_learners.sequential_decision_making.actor_critic_base import (
    ActorCriticBase,
    twin_critic_action_value_update,
)
from pearl.replay_buffers.transition import TransitionBatch
from torch import optim


class ContinuousSoftActorCritic(ActorCriticBase):
    """
    Soft Actor Critic Policy Learner.
    """

    def __init__(
        self,
        state_dim: int,
        action_space: ActionSpace,
        actor_hidden_dims: Iterable[int],
        critic_hidden_dims: Iterable[int],
        actor_learning_rate: float = 1e-3,
        critic_learning_rate: float = 1e-3,
        actor_network_type: ActorNetworkType = GaussianActorNetwork,
        critic_network_type: Type[QValueNetwork] = VanillaQValueNetwork,
        critic_soft_update_tau: float = 0.005,
        exploration_module: Optional[ExplorationModule] = None,
        discount_factor: float = 0.99,
        training_rounds: int = 100,
        batch_size: int = 256,
        entropy_coef: float = 0.2,
        entropy_autotune: bool = True,
    ) -> None:
        super(ContinuousSoftActorCritic, self).__init__(
            state_dim=state_dim,
            action_space=action_space,
            actor_hidden_dims=actor_hidden_dims,
            critic_hidden_dims=critic_hidden_dims,
            actor_learning_rate=actor_learning_rate,
            critic_learning_rate=critic_learning_rate,
            actor_network_type=actor_network_type,
            critic_network_type=critic_network_type,
            use_actor_target=False,
            use_critic_target=True,
            actor_soft_update_tau=0.0,
            critic_soft_update_tau=critic_soft_update_tau,
            use_twin_critic=True,
            exploration_module=exploration_module
            if exploration_module is not None
            else NoExploration(),
            discount_factor=discount_factor,
            training_rounds=training_rounds,
            batch_size=batch_size,
            is_action_continuous=True,
            on_policy=False,
        )

        self._entropy_autotune = entropy_autotune
        print(f"Entropy autotune: {entropy_autotune}")
        if entropy_autotune:
            # initialize the entropy coefficient to 0
            self.register_parameter(
                "_log_entropy",
                torch.nn.Parameter(torch.zeros(1, requires_grad=True)),
            )
            self._entropy_optimizer = optim.AdamW(  # pyre-ignore
                [self._log_entropy], lr=critic_learning_rate, amsgrad=True
            )
            self.register_buffer("_entropy_coef", torch.exp(self._log_entropy).detach())
            self.register_buffer(
                "_target_entropy", -torch.tensor(action_space.shape[0])  # pyre-ignore
            )
        else:
            self.register_buffer("_entropy_coef", torch.tensor(entropy_coef))

    def learn_batch(self, batch: TransitionBatch) -> Dict[str, Any]:
        actor_critic_loss = super().learn_batch(batch)
        state_batch = batch.state  # shape: (batch_size x state_dim)

        if self._entropy_autotune:
            with torch.no_grad():
                _, action_batch_log_prob = self._actor.sample_action(
                    state_batch, get_log_prob=True
                )

            entropy_optimizer_loss = (
                -torch.exp(self._log_entropy)
                * (action_batch_log_prob + self._target_entropy)
            ).mean()

            self._entropy_optimizer.zero_grad()
            entropy_optimizer_loss.backward()
            self._entropy_optimizer.step()

            self._entropy_coef = torch.exp(self._log_entropy).detach()
            {**actor_critic_loss, **{"entropy_coef": entropy_optimizer_loss}}

        return actor_critic_loss

    def _critic_learn_batch(self, batch: TransitionBatch) -> Dict[str, Any]:

        reward_batch = batch.reward  # shape: (batch_size)
        done_batch = batch.done  # shape: (batch_size)

        if done_batch is not None:
            expected_state_action_values = (
                self._get_next_state_expected_values(batch)
                * self._discount_factor
                * (1 - done_batch.float())
            ) + reward_batch  # shape of expected_state_action_values: (batch_size)
        else:
            raise AssertionError("done_batch should not be None")

        loss_critic_update = twin_critic_action_value_update(
            state_batch=batch.state,
            action_batch=batch.action,
            expected_target_batch=expected_state_action_values,
            optimizer=self._critic_optimizer,
            # pyre-fixme
            critic=self._critic,
        )

        return loss_critic_update

    @torch.no_grad()
    def _get_next_state_expected_values(self, batch: TransitionBatch) -> torch.Tensor:
        next_state_batch = batch.next_state  # shape: (batch_size x state_dim)

        # shape of next_action_batch: (batch_size, action_dim)
        # shape of next_action_log_prob: (batch_size, 1)
        (
            next_action_batch,
            next_action_batch_log_prob,
        ) = self._actor.sample_action(next_state_batch, get_log_prob=True)

        next_q1, next_q2 = self._critic_target.get_q_values(
            state_batch=next_state_batch,
            action_batch=next_action_batch,
        )

        # clipped double q-learning (reduce overestimation bias)
        next_q = torch.minimum(next_q1, next_q2)  # shape: (batch_size)
        next_state_action_values = next_q.view(
            self.batch_size, 1
        )  # shape: (batch_size x 1)

        # add entropy regularization
        next_state_action_values = next_state_action_values - (
            self._entropy_coef * next_action_batch_log_prob
        )
        # shape: (batch_size x 1)

        return next_state_action_values.view(-1)

    def _actor_learn_batch(self, batch: TransitionBatch) -> Dict[str, Any]:
        state_batch = batch.state  # shape: (batch_size x state_dim)

        # shape of action_batch: (batch_size, action_dim)
        # shape of action_batch_log_prob: (batch_size, 1)
        (
            action_batch,
            action_batch_log_prob,
        ) = self._actor.sample_action(state_batch, get_log_prob=True)

        q1, q2 = self._critic.get_q_values(
            state_batch=state_batch, action_batch=action_batch
        )  # shape: (batch_size, 1)

        # clipped double q learning (reduce overestimation bias)
        q = torch.minimum(q1, q2)  # shape: (batch_size)
        state_action_values = q.view((self.batch_size, 1))  # shape: (batch_size x 1)

        actor_loss = (
            self._entropy_coef * action_batch_log_prob - state_action_values
        ).mean()

        self._actor_optimizer.zero_grad()
        actor_loss.backward()
        self._actor_optimizer.step()

        return {"actor_loss": actor_loss.item()}