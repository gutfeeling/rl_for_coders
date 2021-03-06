import datetime
import random

from gym.wrappers import Monitor
import numpy as np

class PPOAgent(object):
    """PPO agent implementing actor critic architecture where actor and critic
    do not share parameters
    """

    def compute_advantages_and_value_targets(self,
                                             training_samples_this_episode,
                                             discount_factor, lambda_value
                                             ):
        """Compute and store advantages and value targets using a finite horizon
        version of TD(lambda)

        Arguments:
        training_samples_this_episode -- A list of experiences that belong to
                                          the same episode. Each experience has
                                          the format:

                                          {
                                              "observation" : observation,
                                              "next_observation" : next_obs,
                                              "means" : means,
                                              "vars" : vars,
                                              "action" : action,
                                              "clipped_action" : clipped_action,
                                              "reward" : reward,
                                              "terminal" : terminal,
                                              "value" : value,
                                              "next_value" : next_value,
                                              }
        discount_factor -- Quantifies how much the agent cares about future
                           rewards while learning. Often referred to as gamma in
                           the literature.
        lambda_value -- The lambda in TD(lambda)
        """
        # Recursively compute advanatages, starting from the last experience
        advantage = 0

        for experience in reversed(training_samples_this_episode):

            # Compute TD error for each experience
            target = experience["reward"]
            if not experience["terminal"]:
                target += discount_factor*experience["next_value"]
            td_error = target - experience["value"]

            advantage = (
                td_error +
                discount_factor*lambda_value*advantage
                )
            value_target = advantage + experience["value"]

            # Store the computed advantage and value target
            experience["advantage"] = advantage
            experience["value_target"] = value_target

        return training_samples_this_episode

    def perform_training_step(self, actor, critic, training_samples,
                              minibatch_size, epochs
                              ):
        """Train the actor and critic on experiences

        Arguments:
        actor -- The actor instance
        critic -- The critic instance
        training_samples -- A list of experiences having the format
                            {
                                "observation" : observation,
                                "next_observation" : next_observation,
                                "means" : means,
                                "vars" : vars,
                                "action" : action,
                                "clipped_action" : clipped_action,
                                "reward" : reward,
                                "terminal" : terminal,
                                "value" : value,
                                "next_value" : next_value,
                                "advantage" : advantage,
                                "value_target" : value_target
                                }
        minibatch_size -- Minibatch size for training the actor and critic
        epochs -- Number of epochs of training on one set of experiences
        """

        observations = np.array([
            experience["observation"]
            for experience in training_samples
            ])

        advantages = np.array([
            [experience["advantage"],]
            for experience in training_samples
            ])

        actions = np.array([
            experience["action"]
            for experience in training_samples
            ])

        actor_targets = np.array([
            experience["means"]
            for experience in training_samples
            ])

        critic_targets = np.array([
            experience["value_target"]
            for experience in training_samples
            ])

        actor.update_weights(
            observations, actor_targets, advantages, actions, minibatch_size,
            epochs
            )
        critic.update_weights(
            observations, critic_targets, minibatch_size, epochs
            )

    def test(self, testing_env, total_number_of_episodes, actor, render):
        """Test the PPO agent for a number of episodes and return the average
        reward per episode

        testing_env -- A Gym environment (wrapped or vanilla) used for testing.
                       This may be different from training environment. For
                       example, we might be scaling the rewards in the learning
                       environment. But we want to benchmark performance in a
                       testing environment where the rewards are not scaled.

        total_number_of_episodes -- Test for this many episodes.
        actor -- The actor instance to use for making decisions.
        render -- A Boolean indicating whether to render the environment or not.
        """

        # Total rewards obtained over all testing episodes
        total_rewards = 0

        for episode_number in range(total_number_of_episodes):

            # Start an episode
            observation = testing_env.reset()

            while True:

                # If render is True, show the current situation
                if render:
                    testing_env.render()

                policy = actor.get_policies(np.array([observation]))[0]
                action = actor.get_actions(np.array([policy]))[0]

                # The actor may not keep the actions within the bounds accepted
                # by the environment. Therefore, we clip the action manually to
                # make it conform to the bounds.
                clipped_action = np.clip(
                    action,
                    testing_env.action_space.low,
                    testing_env.action_space.high
                    )

                next_observation, reward, done, info = (
                    testing_env.step(clipped_action)
                    )

                observation = next_observation

                total_rewards += reward

                if done:
                    break

        testing_env.close()

        # Compute average reward per episode
        average_reward = total_rewards/float(total_number_of_episodes)
        return average_reward

    def train(self, actor, critic, discount_factor, lambda_value, learning_env,
              testing_env, horizon, minibatch_size, epochs, total_observations,
              test_interval, total_number_of_testing_episodes,
              gym_training_logs_directory_path, gym_testing_logs_directory_path
              ):
        """Train the PPO agent

        actor -- The actor instance
        critic -- The critic instance
        discount_factor -- Quantifies how much the agent cares about future
                           rewards while learning. Often referred to as gamma in
                           the literature.
        lambda_value -- The lambda in TD(lambda)
        learning_env -- A Gym environment (wrapped or vanilla) used for learning
        testing_env -- A Gym environment (wrapped or vanilla) used for testing.
                       This may be different from learning_env. For example, we
                       might be scaling the rewards in the learning environment.
                       But we want to benchmark performance in a testing
                       environment where the rewards are not scaled.
        horizon -- Number of experiences to collect before performing a training
                   step. Must be a integer multiple of minibatch_size.
        minibatch_size -- Minibatch size for training the actor and critic.
        epochs -- Number of epochs of training on one set of experiences
        total_observations -- Train till this observation number
        test_interval -- Test after this many observations
        total_number_of_testing_episodes -- Number of episodes to test the agent
                                            in every testing round
        gym_training_logs_directory_path - Directory to save automatic Gym logs
                                           related to training. We save the
                                           rewards for every learning episode.
        gym_testing_logs_directory_path - Directory to save automatic Gym logs
                                          related to testing. We save a video
                                          for the first test episode.
        """

        # We will fill training_samples with the agent's experience till it
        # reaches a size equal to horizon. Then we will train the actor
        # and critic on this data. After training is done, we will empty the
        # list and repeat the process for the next sequence of experiences.
        training_samples = []

        # To make computing advantages and value function targets easier, we
        # put the experiences first in a different list
        # training_samples_this_episode. When the episode ends or horizon is
        # reached (whichever happens earlier), we compute advantages and
        # value function targets using this list. Then the list is emptied
        # and the data transfered to the other list training_samples.
        training_samples_this_episode = []

        # This keeps track of the number of observations made so far
        observation_number = 0

        # Keep count of the episode number
        episode_number = 1

        # The learning env should always be wrapped by the Monitor provided
        # by Gym. This lets us automatically save the rewards for every episode.

        learning_env = Monitor(
            learning_env, gym_training_logs_directory_path,
            # Don't want video recording during training, only during testing
            video_callable = False,
            # Write after every reset so that we don't lose data for
            # prematurely interrupted training runs
            write_upon_reset = True,
            )

        while observation_number < total_observations:

            # Start of an episode
            observation = learning_env.reset()

            # Predicted value for this observation
            value = critic.get_value(np.array([observation]))[0][0]

            total_rewards_obtained_in_this_episode = 0

            while True:

                policy = actor.get_policies(np.array([observation]))[0]
                action = actor.get_actions(np.array([policy]))[0]

                # The actor may not keep the actions within the bounds accepted
                # by the environment. Therefore, we clip the action manually to
                # make it conform to the bounds.
                clipped_action = np.clip(
                    action,
                    learning_env.action_space.low,
                    learning_env.action_space.high
                    )

                next_observation, reward, done, info = (
                    learning_env.step(clipped_action)
                    )

                # Predicted value of the next observation, necessary for
                # calculating TD error
                next_value = (
                    critic.get_value(np.array([next_observation]))[0][0]
                    if not done else 0
                    )

                experience = {
                    "observation" : observation,
                    "next_observation" : next_observation,
                    "means" : policy["means"],
                    "vars" : policy["vars"],
                    "action" : action,
                    "clipped_action" : clipped_action,
                    "reward" : reward,
                    "terminal" : done,
                    "value" : value,
                    "next_value" : next_value,
                    }

                training_samples_this_episode.append(experience)

                observation = next_observation
                value = next_value

                observation_number += 1
                # Test the current performance after every test_interval
                if observation_number % test_interval == 0:
                    # The testing env is also wrapped by a Monitor so that we
                    # can take automatic videos during testing. We will take a
                    # video for the very first testing episode.

                    video_callable = lambda count : count == 0

                    # Since the environment is closed after every testing round,
                    # the video for different testing round will end up having
                    # the same name! To differentiate the videos, we pass
                    # an unique uid parameter.

                    monitored_testing_env = Monitor(
                        testing_env, gym_testing_logs_directory_path,
                        video_callable = video_callable,
                        resume = True,
                        uid = observation_number / test_interval
                        )

                    # Run the test
                    average_reward = self.test(
                        monitored_testing_env,
                        total_number_of_episodes =
                            total_number_of_testing_episodes,
                        actor = actor,
                        render = False
                        )
                    print(
                        "[{0}] Episode number : {1}, Observation number : {2} "
                        "Average reward (100 eps) : {3}".format(
                            datetime.datetime.now(), episode_number,
                            observation_number, average_reward
                            )
                        )

                total_rewards_obtained_in_this_episode += reward

                ## Training starts here

                # If previous episodes ended quickly before we could reach the
                # horizon, these experiences have already been transfered to
                # training_samples. So, to get the total number of experiences
                # gathered since the last training step, we have sum up the
                # experiences gathered in this episode and the experiences
                # from previous episodes which have been transferred to
                # training_samples.
                number_of_experiences_since_last_training_step = (
                    len(training_samples_this_episode) +
                    len(training_samples)
                    )

                # If horizon is reached or the episode ended, we compute
                # advantages and value targets using
                # training_samples_this_episode. The experiences are then
                # transfered to the list training_samples. Finally
                # training_samples_this_episode is emptied to accomodate
                # further experiences.
                if (number_of_experiences_since_last_training_step == horizon or
                        done):
                    training_samples_this_episode_with_targets = (
                        self.compute_advantages_and_value_targets(
                            training_samples_this_episode, discount_factor,
                            lambda_value
                            )
                        )
                    training_samples += (
                        training_samples_this_episode_with_targets
                        )
                    training_samples_this_episode = []

                # If horizon is reached, we train the actor and critic on the
                # stored experiences. Then we forget about those experiences
                # by emptying training_samples.
                if number_of_experiences_since_last_training_step == horizon:
                    self.perform_training_step(
                        actor, critic, training_samples, minibatch_size, epochs
                        )
                    training_samples = []

                    # After a round of training, the actor and critic weights
                    # have changed. So we use the updated model to compute the
                    # value function instead of using the value function
                    # predicted by the older models.
                    value = critic.get_value(np.array([next_observation]))[0]

                # Start over when the episode ends
                if done:
                    episode_number += 1
                    break

            print(
                "[{0}] Episode number : {1}, Obervation number: {2}, "
                "Reward in this episode : {3}".format(
                    datetime.datetime.now(), episode_number - 1,
                    observation_number, total_rewards_obtained_in_this_episode
                    )
                )
        learning_env.close()

        # There's a bug in the Gym Monitor. The Monitor's close method does not
        # close the wrapped environment. This makes the script exit with an
        # error if the environment is being rendered at some point. To make
        # this error go away, we have to close the unwrapped testing
        # environment. The learning environment is not being rendered, so we
        # don't need to bother about that.
        testing_env.env.close()
