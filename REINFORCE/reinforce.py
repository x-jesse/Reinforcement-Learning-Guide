"""
    ===========================================================
    Welcome to REINFORCE (aka. Monte Carlo Policy Gradient)!
    ===========================================================

    REINFORCE is probably one of the simpler RL algorithms for model-free reinforcement learning,
    but don't worry if it feels overwhelming at first. There's a lot of different concepts and
    terminology used in ML/AI fields, and it takes a while to get used to them. Feel free to pull
    up the glossary - I try to provide useful definitions and links to useful resources as much
    as possible. :))

    Though REINFORCE is not widely used today due to its limitations, developing a solid understanding 
    of it is an excellent prerequisite to learning what the more complex algorithms do. The
    implementation is not too long - just <100 lines of code! But there are some nuances that
    require a bit of math to fully understand. 

    This section of the guide will serve as a deep-dive into the concepts and driving principles 
    behind the REINFORCE algorithm. 

    REINFORCE, or Monte Carlo policy gradient, is a RL method based on gradient ascent. We want
    to optimize our policy in the direction of maximal reward. The general process is:

        1. Run an epoch, recording information as we go. This includes states, actions, and rewards.

        2. After termination, we update our policy using *Policy Gradient Theorem*.

        3. Repeat until convergence.

    Additional notes:
    - REINFORCE should not be confused with VPG (vanilla policy gradient). Though similar, they
    are slightly different in their calculation of return.
    - This algorithm is the direct implmementation of the pseudo-code from "Intro. to RL" by 
    Richard S. Sutton and Andrew G. Barto. Feel free to check out that book for additional
    explanations!

    Please note: this section does assume you have a basic understanding of Python and Pytorch
    syntax, but it is by no means required to understand the content here.

    Happy learning! <3

"""

import gymnasium as gym
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.distributions import Categorical
from collections import deque

"""
Let's start with a description of our environment. The problem we want to solve is simple:
balance a pole on a cart in a 2D linear environment. Our agent will act in one of two ways:
move the cart right, or move the cart left. It acts by applying a fixed force to one side of
the cart. The goal is to keep the pole upright for as long as possible. The agent receives a
reward (capped at 500) for each timestep the pole is upright, and the episode terminates when 
the pole falls below a certain elevation.

You can find detailed documentation here:
https://gymnasium.farama.org/environments/classic_control/cart_pole/

"""

# This is a standard feed-forward neural network :)
# Optional reading: https://en.wikipedia.org/wiki/Feedforward_neural_network
class FeedForward(nn.Module):
    """
    We begin with a simple PyTorch neural network. This will serve as our policy - 
    a way for us to sample actions. Initially, all the weights will be random;
    our actions will be nonsensical and arbitrary. But as we learn, our policy
    will eventually converge to the optimal one, and our agent should consistently 
    be able to achieve the maximum reward of 500.

    """

    def __init__(self, n_obs, n_actions):
        super().__init__()
        # the number of nodes per layer is pretty arbitrary
        # as long as the network is sufficiently complex to solve our problem
        # it doesn't really matter how many nodes we have
        # (though simpler networks will usually train faster)
        self.l1 = nn.Linear(n_obs, 64)
        self.l2 = nn.Linear(64, n_actions)
    
    def forward(self, x):
        # ReLU activation
        # Optional reading: https://en.wikipedia.org/wiki/Rectifier_(neural_networks)
        x = F.relu(self.l1(x))
        return self.l2(x)

# we can set our model to run on GPU or Apple Silicon if it's available
# better hardware = faster training
device = "cpu"
if torch.cuda.is_available():
    device = "cuda"
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    device = "mps"

# creates the environment
env = gym.make('CartPole-v1', render_mode=None)
state, info = env.reset()

# initializes our policy
policy = FeedForward(env.observation_space.shape[0], env.action_space.n)
policy.to(device)

# our agent should perform pretty well after 200 iterations
# in other words, our policy should converge after 200 episodes
max_eps = 100

# we won't discuss optimizers here - just think of them as a function that performs backpropagation
# Optional reading: 
optimizer = torch.optim.Adam(policy.parameters(), lr=0.01)

# plotting
plot_info = []

# training loop training loop training loop training loop 
for n_epoch in range(max_eps):
    """
    This is our training loop - the place where all the math happens. We'll
    go through it in order, starting from policy initialization, to return calculation,
    and finally gradient updating via backpropagation.

    If you're not familiar with machine learning, feel free to skip this next paragraph.
    If you are, I'd like to draw some connections between training neural networks in RL vs
    other types of ML. There are many ways to train a neural network to perform certain tasks,
    and RL does take advantage of that by using neural networks as a policy. However, unlike
    some other types of ML, such as supervised learning, the loss calculation is not well-defined.
    
    In RL, we need to define our own metrics - and this is the challenge that many RL algorithms
    try to tackle, by providing different ways for us to update our policies. 
    
    """
    cum_reward = 0
    states, actions, rewards = [], [], []
    saved_log_probs = []
    state, info = env.reset()

    # loop until our episode terminates
    while True:
        # we need to wrap our state in an extra dimension,
        # otherwise PyTorch gets angry when we try to calculate loss later
        state = torch.tensor(state, device=device).unsqueeze(0)
        # gets the logit outputs from our policy
        logits = policy(state)

        # we convert our logits into a categorical probability distribution
        # so we can sample an action from it
        # recall that we want to balance exploration vs exploitation:
        # always selecting the action with the highest probability won't lead to exploration
        action_distr = Categorical(logits=logits)
        action = action_distr.sample()

        # tracks our actions and the sampled log probabilities from our policy
        # log probabilities are a useful optimization to have, since they reduce computation time
        actions.append(action)
        saved_log_probs.append(action_distr.log_prob(action))
        
        # env.step() tells the environment what action we want to take - given by action.item()
        new_state, reward, terminated, truncated, info = env.step(action.item())

        # track our states, rewards, and cumulative reward (return)
        states.append(new_state)
        rewards.append(reward)
        cum_reward += reward
        
        # end the loop if our state is terminal
        if terminated or truncated:
            break
        # update state
        state = new_state
    
    # discount factor hyperparameter - typically set to somewhere around ~1
    # (but not greater than 1)
    gamma = 0.99
    discounted_reward = 0
    total_rewards = deque()

    """
    We want to compute our discounted reward here. Recall that for environments where
    we can potentially have very high timesteps, we want our reward series to remain finite.
    It would a problem for us if our return approached infinity, so we introduce a discount
    factor. Strictly speaking, OpenAI Gymnasium has a built in condition that prevents episodes
    from exceeding a certain length, so infinite-timestep episodes aren't really a concern. 
    Empirically though, introducing a discount factor is beneficial to assist convergence
    and decrease variance in our gradient computation, so there's no downside to including it.
    
    Our discounted return calculation takes the form of a repeated sum, looped starting from the
    end of the rewards array:
        
        discounted_reward = r + gamma * discounted_reward

    This might seem weird at first, since we usually calculate our 
    """

    for r in rewards[::-1]:
        discounted_reward = r + gamma * discounted_reward
        total_rewards.appendleft(discounted_reward)
    total_rewards = torch.tensor(total_rewards, device=device)
    total_rewards = (total_rewards - total_rewards.mean()) / total_rewards.std()

    states = torch.tensor(np.array(states), device=device)
    logits = policy(states)
    losses = []
    for log_prob, r in zip(saved_log_probs, total_rewards):
        losses.append(-r * log_prob)

    loss = torch.cat(losses).sum()
    print(n_epoch, cum_reward, loss.item())
    plot_info.append((n_epoch, cum_reward, loss.item()))

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()

np.save("ref", np.array(plot_info))
torch.save(policy, "policy")

env.close()


