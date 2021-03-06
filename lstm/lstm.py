import torch
import torch.nn as nn
import torch.optim as optim
from .dataset import PreTrainDataset
import numpy as np
from torch.utils.data import DataLoader
from tqdm import tqdm


class LSTM(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim, id_dim, layer_num, lr, device):
        super().__init__()
        self.lstm = nn.LSTM(in_dim, hidden_dim, layer_num, batch_first=True)
        self.relu = nn.ReLU()
        self.id_fc = nn.Linear(hidden_dim, id_dim)
        self.device = device
        self.to(device)
        self.optimizer = optim.Adam(self.parameters(), lr=lr)
        self.criterion = nn.CrossEntropyLoss().to(device)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.relu(out)
        out = self.id_fc(out)
        return out

    def pretrain(self, agents, batch_size, epochs, rounds, sample_size):
        self.train()
        self.apply(_initialize_weights)
        dataset = PreTrainDataset(agents, rounds, sample_size)
        dataloader = DataLoader(dataset, batch_size = batch_size)

        for epoch in range(epochs):
            epoch_accs = []
            for batch in tqdm(dataloader):
                self._train_batch(batch, epoch_accs)
            print(np.mean(epoch_accs))

    def predict_id(self, input):
        """Predicts the ID of an agent based on the input"""
        out = self(input)
        id_logits = out[:, -1, :]
        pred_id = id_logits.argmax(dim=-1)
        return pred_id.item(), id_logits

    def rebuild_input(self, nn_action, opp_action, prev_input):
        curr_input = [0, 0]
        curr_input[0] = nn_action
        curr_input[1] = opp_action
        curr_input = torch.Tensor(curr_input).to(self.device).unsqueeze(0)
        return torch.cat([prev_input, curr_input]).unsqueeze(0)

    def learn(self, id_logits, id):
        """Optimizes model weights based on current input, previous input, expected id, and actual id"""
        id_loss = self.criterion(id_logits, id)
        id_loss.backward()
        self.optimizer.step()

    def build_input_vector(self, prev_agent_choice):
        """Creates NN input vector"""
        input = [0, 0]
        input[1] = prev_agent_choice
        return torch.Tensor(input).to(self.device).unsqueeze(0).unsqueeze(0)

    def build_id_vector(self, agent):
        """Find id of agent (another input to NN for regularization)"""
        id = [agent.id()]
        id = torch.Tensor(id).to(self.device)
        return id.to(torch.int64)

    def save(self, fname):
        torch.save(self.state_dict(), f"lstm/models/{fname}.pth")

    def load(self, fname):
        self.load_state_dict(torch.load(f"lstm/models/{fname}.pth"))
        self.to(self.device)
    
    def _train_batch(self, batch, epoch_accs):
        """Pretrains weights based on a batch of inputs"""
        input = batch["input"].type(torch.FloatTensor).to(self.device)
        output = batch["output"].to(self.device)
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