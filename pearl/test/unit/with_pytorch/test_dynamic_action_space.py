#!/usr/bin/env fbpython
# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.
import unittest

import torch
from pearl.action_representation_modules.one_hot_action_representation_module import (
    OneHotActionTensorRepresentationModule,
)
from pearl.policy_learners.sequential_decision_making.deep_q_learning import (
    DeepQLearning,
)
from pearl.replay_buffers.sequential_decision_making.fifo_off_policy_replay_buffer import (
    FIFOOffPolicyReplayBuffer,
)

from pearl.utils.instantiations.spaces.discrete_action import DiscreteActionSpace


class TestDynamicActionSpaceReplayBuffer(unittest.TestCase):
    def test_basic(self) -> None:
        """
        Test setup:
        - assume max_number_actions = 5
        - push a transition with dynamic action space of [0, 2, 4] in action space
        - after push, expect available_mask = [0, 0, 0, 1, 1] and action space to be [
            [0],
            [2],
            [4],
            [0],
            [0],
        ]
        - expect available_mask = [0, 0, 0, 1, 1] and one hot representation to be [
            [1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0],
            [1, 0, 0, 0, 0],
        ]
        """
        state_dim = 10
        current_action_space = DiscreteActionSpace(
            [torch.tensor([i]) for i in [0, 2, 4]]
        )
        next_action_space = DiscreteActionSpace([torch.tensor([i]) for i in [0, 3]])
        action_representation_module = OneHotActionTensorRepresentationModule(
            max_number_actions=5
        )
        replay_buffer = FIFOOffPolicyReplayBuffer(capacity=10)
        replay_buffer.push(
            state=torch.zeros(state_dim),
            action=current_action_space.sample(),
            reward=0,
            next_state=torch.zeros(state_dim),
            curr_available_actions=current_action_space,
            next_available_actions=next_action_space,
            done=False,
            max_number_actions=action_representation_module.max_number_actions,
        )
        batch = replay_buffer.sample(1)
        current_available_actions = batch.curr_available_actions
        current_available_actions_mask = batch.curr_available_actions_mask
        self.assertIsNotNone(current_available_actions)
        self.assertTrue(
            torch.equal(
                current_available_actions,
                torch.tensor([[[0.0], [2.0], [4.0], [0.0], [0.0]]]),
            )
        )
        self.assertIsNotNone(current_available_actions_mask)
        self.assertTrue(
            torch.equal(
                current_available_actions_mask,
                torch.tensor([[False, False, False, True, True]]),
            )
        )

        next_available_actions = batch.next_available_actions
        next_available_actions_mask = batch.next_available_actions_mask
        self.assertIsNotNone(next_available_actions)
        self.assertTrue(
            torch.equal(
                next_available_actions,
                torch.tensor([[[0.0], [3.0], [0.0], [0.0], [0.0]]]),
            )
        )
        self.assertIsNotNone(next_available_actions_mask)
        self.assertTrue(
            torch.equal(
                next_available_actions_mask,
                torch.tensor([[False, False, True, True, True]]),
            )
        )

        policy_learner = DeepQLearning(
            state_dim=state_dim,
            hidden_dims=[3],
            training_rounds=1,
            action_representation_module=action_representation_module,
        )

        batch = policy_learner.preprocess_batch(batch)
        current_available_actions = batch.curr_available_actions
        current_available_actions_mask = batch.curr_available_actions_mask
        self.assertIsNotNone(current_available_actions)
        self.assertTrue(
            torch.equal(
                current_available_actions,
                torch.tensor(
                    [
                        [
                            [1, 0, 0, 0, 0],
                            [0, 0, 1, 0, 0],
                            [0, 0, 0, 0, 1],
                            [1, 0, 0, 0, 0],
                            [1, 0, 0, 0, 0],
                        ]
                    ]
                ),
            )
        )
        self.assertIsNotNone(current_available_actions_mask)
        self.assertTrue(
            torch.equal(
                current_available_actions_mask,
                torch.tensor([[False, False, False, True, True]]),
            )
        )

        next_available_actions = batch.next_available_actions
        next_available_actions_mask = batch.next_available_actions_mask
        self.assertIsNotNone(next_available_actions)
        self.assertTrue(
            torch.equal(
                next_available_actions,
                torch.tensor(
                    [
                        [
                            [1, 0, 0, 0, 0],
                            [0, 0, 0, 1, 0],
                            [1, 0, 0, 0, 0],
                            [1, 0, 0, 0, 0],
                            [1, 0, 0, 0, 0],
                        ]
                    ]
                ),
            )
        )
        self.assertIsNotNone(next_available_actions_mask)
        self.assertTrue(
            torch.equal(
                next_available_actions_mask,
                torch.tensor([[False, False, True, True, True]]),
            )
        )
