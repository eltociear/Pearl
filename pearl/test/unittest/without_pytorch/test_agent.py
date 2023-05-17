#!/usr/bin/env fbpython
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
import unittest

import gym
from pearl.contextual_bandits.dummy_contextual_bandit_policy_learner import (
    DummyContextualBanditPolicyLearner,
)

from pearl.contextual_bandits.reward_is_equal_to_ten_times_action_contextual_bandit_environment import (
    RewardIsEqualToTenTimesActionContextualBanditEnvironment,
)
from pearl.gym.gym_environment import GymEnvironment
from pearl.online_learning.online_learning import episode_return, online_learning
from pearl.pearl_agent import PearlAgent

from pearl.policy_learners.tabular_q_learning import TabularQLearning
from pearl.utils.environments import FixedNumberOfStepsEnvironment


class TestAgentWithoutPyTorch(unittest.TestCase):
    """
    A collection of Agent tests not involving PyTorch (this saves around 100 secs in test loading).
    For tests involving PyTorch, use see test/with_pytorch.
    """

    def test_online_rl(self) -> None:
        env = FixedNumberOfStepsEnvironment(number_of_steps=100)
        agent = PearlAgent()
        online_learning(agent, env)

    def test_tabular_q_learning_online_rl(self) -> None:
        env = GymEnvironment("FrozenLake-v1", is_slippery=False)
        agent = PearlAgent(policy_learner=TabularQLearning())

        online_learning(agent, env, number_of_episodes=1000)

        for _ in range(100):  # Should always reach the goal
            assert episode_return(agent, env, learn=False, exploit=True) == 1.0

    def test_contextual_bandit_with_tabular_q_learning_online_rl(self) -> None:
        number_of_actions = 5
        max_action = number_of_actions - 1
        env = RewardIsEqualToTenTimesActionContextualBanditEnvironment(
            action_space=gym.spaces.Discrete(number_of_actions)
        )

        # Because a contextual bandit environment is simply a regular Environment
        # with episodes lasting a single step, we can solve them with regular
        # RL algorithms such as tabular Q-learning.
        # This test ensures that is true (that even a non-CB method works with the CB environment).
        # In practice, CB-specific algorithms will be used.
        agent = PearlAgent(
            policy_learner=TabularQLearning(exploration_rate=0.1, learning_rate=0.1)
        )

        online_learning(agent, env, number_of_episodes=10000)

        # Should have learned to use action max_action with reward equal to max_action * 10
        for _ in range(100):
            assert (
                episode_return(agent, env, learn=False, exploit=True) == max_action * 10
            )

    def test_contextual_bandit_with_dummy_policy_learner_online_rl(self) -> None:
        # Using a dummy contextual bandit policy learner.
        # The dummy only exemplifies how to implement a CB algorithm more conveniently;
        # it does not actually learn.
        number_of_actions = 5
        env = RewardIsEqualToTenTimesActionContextualBanditEnvironment(
            action_space=gym.spaces.Discrete(number_of_actions)
        )
        agent = PearlAgent(policy_learner=DummyContextualBanditPolicyLearner())

        online_learning(agent, env, number_of_episodes=10000)

        # Dummy does not actually learn, so there are no accuracy tests
