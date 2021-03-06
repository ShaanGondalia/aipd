from agent import agents as ag
from tqdm import tqdm
from params import *
from lstm.lstm import LSTM
import matplotlib.pyplot as plt
import qtable.qagent as qag
import qtable.qlearn as ql
import numpy as np
import torch.nn.functional as nnf
import torch
import pickle
import random
import math
import imageio as iio

CB91_Blue = '#2CBDFE'
CB91_Green = '#47DBCD'
CB91_Pink = '#F3A0F2'
CB91_Purple = '#9D2EC5'
CB91_Violet = '#661D98'
CB91_Amber = '#F5B14C'
color_list = [CB91_Blue, CB91_Pink, CB91_Green, CB91_Amber,
              CB91_Purple, CB91_Violet]
plt.rcParams['axes.prop_cycle'] = plt.cycler(color=color_list)

class Game():
    def __init__(self, agents_config):
        self.agents = ag.Agents(agents_config) # The agents to play against in the tournament
        self.lstm = LSTM(IN, LSTM_HIDDEN, OUT, len(self.agents.agents), LSTM_LAYERS, LSTM_LR, DEVICE)
        self.q_agents = {}
        for agent in self.agents.agents:
            self.q_agents[agent.id()] = qag.QAgent(lr = QTABLE_LR, 
                discount=QTABLE_DISCOUNT, epsilon=QTABLE_EPSILON_TRAIN, 
                decay_rate=QTABLE_DECAY_RATE, min_e=QTABLE_MIN_EPSILON, memory=QTABLE_MEMORY)
        self.generations = GENERATIONS
        self.interactions = INTERACTIONS
        self.reproduction_rate = REPRODUCTION_RATE

    def train_all(self, visualize=False):
        self.train_lstm()
        self.train_qtables(visualize)

    def train_lstm(self):
        print("Training LSTM")
        self.lstm.pretrain(self.agents, LSTM_PRETRAIN_BATCH_SIZE, 
            LSTM_PRETRAIN_EPOCHS, TEST_ROUNDS, LSTM_PRETRAIN_SAMPLE_SIZE)

    def train_qtables(self, visualize=False):
        print("Training QTables")
        for agent in self.agents.agents:
            ql.train(self.q_agents[agent.id()], agent, QTABLE_TRAIN_EPOCHS, 
                TEST_ROUNDS, REWARD, visual=visualize, name=agent.name)

    def save_all(self, fname):
        self.save_lstm(fname)
        self.save_qtables(fname)

    def save_lstm(self, fname):
        print(f"Saving LSTM to file: lstm/models/{fname}.pth")
        self.lstm.save(fname)

    def save_qtables(self, fname):
        print(f"Saving Qtables to file: qtable/models/{fname}.pickle")
        with open(f'qtable/models/{fname}.pickle', 'wb') as handle:
            pickle.dump(self.q_agents, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def load(self, fname):
        print(f"Loading Models from file: {fname}")
        self.lstm.load(fname)
        with open(f'qtable/models/{fname}.pickle', 'rb') as handle:
            self.q_agents = pickle.load(handle)

    def visualize_lstm(self, fname):
        for agent in self.agents.agents:
            confidence_file = f'lstm/visuals/confidence/{fname}_{agent.name}.png'
            self.visualize_lstm_confidence(agent, confidence_file)
        accuracy_file = f'lstm/visuals/accuracy/{fname}.png'
        self.visualize_lstm_accuracy(accuracy_file)

    def play(self):
        print("Playing Game")
        self.lstm.eval()
        accuracies = {}
        for epoch in range(TEST_EPOCHS):
            print("EPOCH %d" % epoch)
            errors = 0
            total_reward = 0
            for i in tqdm(range(TEST_GAMES)):
                agent = self.agents.get_random_agent()
                reward, error = self._play_one_game(agent, TEST_ROUNDS)
                errors += error
                total_reward += reward
                agent.reset()

            frac = (TEST_GAMES-errors)/TEST_GAMES
            print("Prediction Accuracy: %.2f" % frac)
            print(f"Total Reward: {total_reward}")
            print(f"Average Reward per Game: {total_reward/TEST_GAMES}")
            print(f"Average Reward per Round: {total_reward/(TEST_GAMES*TEST_ROUNDS)}")

    def _play_one_game(self, agent, rounds):
        """Plays a single game against an agent, comprised of ROUNDS iterations"""
        prev_agent_choice = 0 # This should probably get replaced (assume cooperate first)
        prev_agent_moves = []
        prev_nn_moves = []
        reward = 0
        input = self.lstm.build_input_vector(prev_agent_choice)
        id = self.lstm.build_id_vector(agent)
        # Play ROUNDS iterations of the prisoners dilemma against the same agent
        for _ in range(rounds):
            prev_moves = np.array([prev_nn_moves, prev_agent_moves]).T
            pred_id, id_logits = self.lstm.predict_id(input)
            probs = nnf.softmax(id_logits, dim=1).detach().cpu().numpy()
            agent_action = int(agent.play())
            # TODO: Implement Linear combination of results here
            nn_action = self.q_agents[pred_id].pick_action(prev_moves, False)
            input = self.lstm.rebuild_input(nn_action, agent_action, input[0])
            agent.update(nn_action)
            prev_agent_moves.append(agent_action)
            prev_nn_moves.append(nn_action)
            reward += ql.get_reward(nn_action, agent_action, REWARD)[0]
        # self.lstm.learn(id_logits, id)

        return reward, 0 if pred_id == agent.id() else 1

    def visualize_lstm_accuracy(self, save_path, defect_first_ids = [], max_length = 20) :
        self.lstm.eval()
        accuracies = {}
        print("Beginning Accuracy Evaluation")
        for length in range(1, max_length+1):
            errors = 0
            for game in tqdm(range(TEST_GAMES)):
                agent = self.agents.get_random_agent()
                reward, error = self._play_one_game(agent, length) 
                errors += error
                agent.reset()

            frac = (TEST_GAMES-errors)/TEST_GAMES
            print("Prediction Accuracy with Length %s: %.2f" %(length, frac))
            accuracies[length] = frac

        x = list(accuracies.keys())
        y = list(accuracies.values())
        plt.figure()
        plt.plot(x, y, 'o-')
        plt.ylim([0,1])
        plt.xlim([0, max_length+1])
        plt.grid()
        plt.xlabel("Number of Rounds Played")
        plt.ylabel("Prediction Accuracy")
        plt.title("Rounds vs Accuracy")
        plt.savefig(save_path, dpi = 200)
        plt.show()

    def visualize_lstm_confidence(self, agent, save_path, max_length=50):
        self.lstm.eval()
        confidences = []
        print("Beginning Confidence Evaluation")
        input = self.lstm.build_input_vector(agent.play())
        for i in range(1, max_length+1):
            pred_id, id_logits = self.lstm.predict_id(input)
            nn_action = np.random.randint(2)
            agent_action = int(agent.play())
            input = self.lstm.rebuild_input(nn_action, agent_action, input[0])
            agent.update(nn_action)

            probs = torch.softmax(id_logits.squeeze().detach().cpu(), dim=0)
            confidences.append(probs.numpy())

        predicted_id = id_logits.argmax(dim=-1).item()
        print("The Predicted ID is: %d" % predicted_id)

        confidences = np.array(confidences)
        plt.figure()
        for i in range(confidences.shape[1]):
            plt.plot(confidences[:, i], label = self.agents.agents[i].name)
            plt.ylim([0,1])
            plt.legend()
            plt.grid()
            plt.xlabel("Rounds Played")
            plt.ylabel("Predicted Probability of Each Agent")
            plt.title(f"Network Confidence Against {agent.name} Agent")
            plt.savefig(save_path, dpi = 200)
        plt.show()
        
    def play_IPD(self, agent0, agent1, reward):
        prev_agent0_moves = []
        prev_agent1_moves = []
        rewards = [0, 0]
        
        # Play ROUNDS iterations of the prisoners dilemma against the same agent
        for _ in range(ROUNDS):
            prev_moves = np.array([prev_agent0_moves, prev_agent1_moves]).T
            agent0_action = int(agent0.play())
            agent1_action = int(agent1.play())
            agent0.update(agent1_action)
            agent1.update(agent0_action)
            prev_agent0_moves.append(agent0_action)
            prev_agent1_moves.append(agent1_action)
            # TODO: use words "move" or "action" consistently
            rewards[0] += ql.get_reward(agent0_action, agent1_action, reward)[0]
            rewards[1] += ql.get_reward(agent0_action, agent1_action, reward)[1]

        return rewards
    
    def natural_selection(self, agents_pre_selection):
        pop_size = len(agents_pre_selection)
        replacements = min(math.floor(self.reproduction_rate * pop_size), pop_size // 2)
        for i in range(replacements):
            agents_pre_selection[i] = agents_pre_selection[-i]
        return agents_pre_selection
    
    def plot_generation(self, tournament_agents, unique_agents, filename):
        side = int(np.ceil(np.sqrt(len(tournament_agents))))
        img = np.full((side*side, 1), unique_agents + 1)
        i = 0
        
        for tournament_agent in tournament_agents:
          img[i] = tournament_agent.id()
          i += 1
          
        img = img.reshape((side, side)).astype(np.uint8)
        plt.figure(figsize=(5,5))
        plt.imshow(img, cmap='gist_ncar', vmin=0, vmax=unique_agents)
        plt.colorbar()
        plt.axis('off')
        plt.savefig(filename)
        plt.close()
        
    def animate_tournament(self, generations, name):
        frames = []
        i = 0
        
        agent_ids = []
        for agent in generations[0]:
          agent_ids.append(agent.id())
        unique_agents = len(np.unique(agent_ids))
        
        for generation in generations:
          filename = 'visuals/images/{name}_generation_{idx}.png'.format(name=name, idx=i)
          self.plot_generation(generation, unique_agents, filename)
          frames.append(iio.imread(filename))
          i += 1
          
        iio.mimsave('visuals/animations/{name}_tournament_animation.gif'.format(name=name), frames, fps=6)

    def graph_tournament(self, generations, name):
        agent_pops = dict()
        for agent in generations[0]:
            agent_pops[agent.name] = []

        for generation in generations:
            for val in agent_pops.values():
                val.append(0)
            for agent in generation:
                agent_pops[agent.name][-1] += 1

        plt.figure(dpi=200)
        for k, v in agent_pops.items():
            plt.plot(np.arange(len(generations)), v, label=k)

        plt.title('Tournament Evolution')
        plt.xlabel('Generation')
        plt.ylabel('Population Size')
        plt.legend(loc='upper left')
        filename = 'visuals/graphs/{name}_tournament_evolution.png'.format(name=name)
        plt.savefig(filename)
        plt.close()

    def tournament(self, visual=False, name='unnamed'):
        generations = []
        generations.append(self.agents.tournament)
        for generation in tqdm(range(self.generations)):
            tournament_agents = self.agents.tournament
            
            rewards = [0] * len(tournament_agents)
            agents_and_rewards = [list(a_r) for a_r in zip(tournament_agents, rewards)]

            for interaction in range(self.interactions):
                random.shuffle(agents_and_rewards)
                for i in range(0, len(agents_and_rewards) - 1, 2):
                    agent0 = agents_and_rewards[i][0]
                    agent1 = agents_and_rewards[i+1][0]
                    reward0, reward1 = self.play_IPD(agent0, agent1, REWARD)
                    agents_and_rewards[i][1] += reward0
                    agents_and_rewards[i+1][1] += reward1
                    
            agents_and_rewards.sort(key=lambda x: x[1])
            agents_pre_selection = [list(a_r) for a_r in zip(*agents_and_rewards)][0]
            
            agents_post_selection = self.natural_selection(agents_pre_selection)
            generations.append(agents_post_selection)
            self.agents.tournament = agents_post_selection
        if visual:
            self.animate_tournament(generations, name)
            self.graph_tournament(generations, name)