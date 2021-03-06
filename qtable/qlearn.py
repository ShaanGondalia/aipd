from tqdm import tqdm 
import numpy as np
import matplotlib.pyplot as plt
import math
import copy
import imageio as iio

def play_IPD(player_1, player_2, rounds, is_training, reward):
    player_1_actions = []
    player_2_actions = []
    total_reward_1 = 0
    total_reward_2 = 0
    curr_moveset = np.array([player_1_actions, player_2_actions]).T
    is_final_round = False
    player_2.val = 0 # Reset opponent's memory

    for j in range(rounds):
      prev_moveset = curr_moveset
      action_1 = player_1.pick_action(prev_moveset, is_training)
      action_2 = player_2.play()
      player_2.update(action_1)

      player_1_actions.append(action_1)
      player_2_actions.append(action_2)
      curr_moveset = np.array([player_1_actions, player_2_actions]).T

      reward_1, reward_2 = get_reward(action_1, action_2, reward)

      total_reward_1 += reward_1
      total_reward_2 += reward_2

      if j == rounds - 1:
        is_final_round = True

      if is_training:
        player_1.reward_action(prev_moveset, curr_moveset, action_1, reward_1, is_final_round)

    return total_reward_1, total_reward_2, curr_moveset

def get_reward(action_1, action_2, reward):
    reward_1 = 0
    reward_2 = 0

    if action_1 == 0 and action_2 == 0: # Both players cooperate
          reward_1 = reward[0][0]
          reward_2 = reward[0][1]
    elif action_1 == 0 and action_2 == 1: # Only player 2 defects
          reward_1 = reward[1][0]
          reward_2 = reward[1][1]
    elif action_1 == 1 and action_2 == 0: # Only player 1 defects
          reward_1 = reward[2][0]
          reward_2 = reward[2][1]
    elif action_1 == 1 and action_2 == 1: # Both players defect
          reward_1 = reward[3][0]
          reward_2 = reward[3][1]

    return reward_1, reward_2

def sigmoid(x, stretch):
  return 1 / (1 + math.exp(-x/stretch))

def plot_qtable(qtable, filename):
  qvals = qtable.values()
  side = int(np.ceil(np.sqrt(len(qvals))))
  img = np.full((side*side, 1), 127.5)
  i = 0
  
  for k in sorted(qtable, key=len):
    img[i] = 127.5 + 255 * (sigmoid(qtable.get(k)[1] - qtable.get(k)[0], 3) - 0.5)
    i += 1
    
  img = img.reshape((side, side)).astype(np.uint8)
  plt.figure(figsize=(5,5))
  plt.imshow(img, cmap='bwr', vmin=0, vmax=255)
  plt.axis('off')
  plt.savefig(filename)
  plt.close()
  
def animate_qtable(player, qtables, name):
  qtable_final = player.get_table()    
  qtable_snapshot = dict.fromkeys(qtable_final, [0,0])
  frames = []
  i = 0

  for qtable in qtables:
    filename = 'qtable/visuals/images/{name}_qtable_{idx}.png'.format(name=name, idx=i)
    qtable_snapshot.update(qtable)
    plot_qtable(qtable_snapshot, filename)
    frames.append(iio.imread(filename))
    i += 1

  iio.mimsave('qtable/visuals/animations/{name}_qtable_animation.gif'.format(name=name), frames, fps=12)

# TRAINING
# TODO: initial state of (0,0) may bias towards whatever the first selected move is in that state (FIXED: by adding is_curious parameter)
# TODO: similar payoffs may bias towards defection since cooperation only makes sense after a few moves (FIXED: by setting MAX learning rate)
# TODO: Q-Table debug "initial state" problem (FIXED: by playing with state logic)
# TODO: fix player memory, state rewards are currently overflowing
# TODO: consider filling the table backwards for efficiency, later rounds before earlier rounds
# TODO: solve problem of players knowing the game length with a probability for ending instead
# TODO: store number of times a state,action pair has been seen to improve learning, curiosity
# TODO: use numba here to speed up training

def train(player_1, player_2, epochs, rounds, reward, verbose=False, visual=False, name='unnamed', granularity=100, early_convergence=False, convergence_epochs=2000):
  max_total_reward_1 = 0
  qtables = []
  qtable_prev = dict()
  qtable_curr = dict()
  consecutive_repeats = 0

  for i in tqdm(range(epochs)):
    total_reward_1, total_reward_2, moveset = play_IPD(player_1, player_2, rounds, True, reward) 
    max_total_reward_1 = max(total_reward_1, max_total_reward_1)
    
    if (i % granularity == 0):
      qtable_curr = copy.deepcopy(player_1.get_table())
      qtables.append(qtable_curr)
    if early_convergence:
        qtable_curr = copy.deepcopy(player_1.get_table())
        if (qtable_curr == qtable_prev):
            consecutive_repeats += 1
            if consecutive_repeats == convergence_epochs:
                if visual:
                    qtables.append(qtable_curr)
                break
        else:
            consecutive_repeats = 0

        qtable_prev = copy.deepcopy(qtable_curr)
      
  if verbose:
    print('Player 1 Max Training Reward Seen:', max_total_reward_1)
    
  if visual:
    animate_qtable(player_1, qtables, name)
     
    

def test(player_1, player_2, epochs, rounds, epsilon, memory, reward, verbose=False):
  # TESTING
  Q_wins = 0
  Q_ties = 0
  Q_loses = 0
  total_rewards_1 = []
  total_rewards_2 = []
  movesets = []
  player_1.set_epsilon(epsilon)

  for i in tqdm(range(epochs)):
    total_reward_1, total_reward_2, moveset = play_IPD(player_1, player_2, rounds, False, reward)    

    if total_reward_1 > total_reward_2:
      Q_wins += 1
    elif total_reward_1 == total_reward_2:
      Q_ties += 1
    else:
      Q_loses += 1

    total_rewards_1.append(total_reward_1)
    total_rewards_2.append(total_reward_2)
    movesets.append(moveset)

  Q_table = player_1.get_table()
  Q_table_actual_size = len(Q_table)
  Q_table_max_size = 0
  for i in range(min(rounds, memory + 1)):
    Q_table_max_size += 4**i
    
  if verbose:
    print('\n')
    print('Player 1 Wins:', Q_wins)
    print('Player 1 Ties:', Q_ties)
    print('Player 1 Losses:', Q_loses)
    print('\n')
    print('Mutual Coop Reward:', rounds * reward[0][0])
    print('Player 1 Avg Reward:', np.mean(total_rewards_1))
    print('Player 2 Avg Reward:', np.mean(total_rewards_2))
    print('\n')
    print('Q-Table Actual Size:', Q_table_actual_size)
    print('Q-Table Max Size:', Q_table_max_size) # Assuming stochastic opponent
    print('\n')
    
    for i in range(1):
      print('Player 1 Reward (Sample Test Game):', total_rewards_1[i])
      print('Player 2 Reward (Sample Test Game):', total_rewards_2[i])
      print(movesets[i])
      print('\n')
      
    i = 0
    for k, v in Q_table.items():
      print(k, v)
      print('\n')
      i += 1
      if i > 3:
          break

