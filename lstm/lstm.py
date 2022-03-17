import torch
import torch.nn as nn
import torch.optim as optim
from .hyper_parameters import *
from .dataset import PreTrainDataset
import numpy as np
from torch.utils.data import DataLoader
from tqdm import tqdm


class LSTM(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim, id_dim, layer_num):
        super().__init__()
        self.lstm = nn.LSTM(in_dim, hidden_dim, layer_num, batch_first=True)
        self.relu = nn.ReLU()
        self.id_fc = nn.Linear(hidden_dim, id_dim)
        self.optimizer = None
        self.criterion = None

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.relu(out)
        out = self.id_fc(out)
        return out

    def pretrain(self):
        dataset = PreTrainDataset()
        dataloader = DataLoader(dataset, batch_size = BATCH_SIZE)
        self.apply(_initialize_weights)
        self.to(DEVICE)
        self.train()

        self.optimizer = optim.Adam(self.parameters(), lr=LR)
        self.criterion = nn.CrossEntropyLoss()
        self.criterion = self.criterion.to(DEVICE)

        for epoch in range(EPOCHS):
            epoch_accs = []
            for batch in tqdm(dataloader):
                self._train_batch(batch, epoch_accs)
            print(np.mean(epoch_accs))

    def predict_id(self, input, agent, id):
        """Predicts the ID of an agent based on the input"""
        out = self(input)
        id_logits = out[:, -1, :]
        pred_id = id_logits.argmax(dim=-1)
        return pred_id.item(), id_logits

    def learn(self, nn_action, opp_action, prev_input, id_logits, id):
        """Optimizes model weights based on current input, previous input, expected id, and actual id"""
        curr_input = [0, 0]

        curr_input[0] = nn_action
        curr_input[1] = opp_action
        curr_input = torch.Tensor(curr_input).to(DEVICE).unsqueeze(0)

        id_loss = self.criterion(id_logits, id)
        id_loss.backward()
        self.optimizer.step()
        return torch.cat([prev_input, curr_input]).unsqueeze(0)

    def build_input_vector(self, prev_agent_choice):
        """Creates NN input vector"""
        input = [0, 0]
        input[1] = prev_agent_choice
        return torch.Tensor(input).to(DEVICE).unsqueeze(0).unsqueeze(0)

    def build_id_vector(self, agent):
        """Find id of agent (another input to NN for regularization)"""
        id = [agent.id()]
        id = torch.Tensor(id).to(DEVICE)
        return id.to(torch.int64)

    def save(self, fname):
        torch.save(self.state_dict(), f"./saved/{fname}")

    def load(self, fname):
        self.load_state_dict(torch.load(f"./saved/{fname}"))
        self.eval()

    def _train_batch(self, batch, epoch_accs):
        """Pretrains weights based on a batch of inputs"""
        input = batch["input"].type(torch.FloatTensor).to(DEVICE)
        output = batch["output"].to(DEVICE)
        pred = self(input)
        pred_logits = pred[:, -1, :]
        loss = self.criterion(pred_logits, output)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        accuracy = _get_accuracy(pred_logits, output)
        epoch_accs.append(accuracy.item())

def _get_accuracy(prediction, label):
    batch_size, _ = prediction.shape
    predicted_classes = prediction.argmax(dim=-1)
    correct_predictions = predicted_classes.eq(label).sum()
    accuracy = correct_predictions / batch_size
    return accuracy

def _initialize_weights(m):
    if isinstance(m, nn.Linear):
        nn.init.xavier_normal_(m.weight)
        nn.init.zeros_(m.bias)
    elif isinstance(m, nn.LSTM):
        for name, param in m.named_parameters():
            if 'bias' in name:
                nn.init.zeros_(param)
            elif 'weight' in name:
                nn.init.orthogonal_(param)