import torch
import torch.nn as nn
import random
import numpy as np
import matplotlib.pyplot as plt
import itertools
from hw3_utils import vocab
import cython

class LangID(nn.Module):
    def __init__(self,
            input_vocab_n,
            embedding_dims,
            hidden_dims,
            lstm_layers,
            output_class_n
            ):
        super(LangID, self).__init__()

        # Saving this so that other parts of the class can re-use it
        self.lstm_dims = hidden_dims
        self.lstm_layers = lstm_layers

        # Our input embedding layer:
        self.input_lookup = nn.Embedding(
                num_embeddings=input_vocab_n,
                embedding_dim=embedding_dims)

        # Note the use of batch_first in the LSTM initialization-
        # this has to do with the layout of the data we
        # use as its input. See the docs for more details
        self.lstm = nn.LSTM(
                input_size=embedding_dims,
                hidden_size=hidden_dims,
                num_layers=lstm_layers,
                batch_first=True)

        # The output softmax classifier: first, the linear layer:
        self.output = nn.Linear(
                in_features=hidden_dims,
                out_features=output_class_n)

        # Then, the actual log-softmaxing:
        # Note that we are using LogSoftmax here, since we want
        # to use negative log-likelihood as our loss function.
        self.softmax = nn.LogSoftmax(dim=2)

    # Expects a (1, n) tensor where n equals the
    # nlength of the input sentence in characters
    # Will return a (output_class_n) tensor- one slot
    # in the first dimension for each possible output class
    def forward(self, sentence_tensor):
        n = sentence_tensor.shape[1]

        input = self.input_lookup(sentence_tensor)

        h0 = torch.randn(self.lstm_layers, 1, self.lstm_dims)
        c0 = torch.randn(self.lstm_layers, 1, self.lstm_dims)

        #output, (hn, cn) = self.lstm(input, (h0, c0))
        output, _ = self.lstm(input, (h0, c0))

        output = self.output(output)

        return self.softmax(output)[0][-1]


    # When we call the forward() method on a PyTorch RNN,
    # we need to provide it with the previous
    # time-point's hidden state (or hidden and memory
    # states, in the case of an LSTM).
    #
    # When the network has not seen any data (i.e., we're
    # looking at a new training example), we can
    # either give it zeroes for its initial hidden value,
    # or random noise. Random noise is a bit better,
    # generally, so we'll start with that.
    def init_hidden(self):
        h0 = torch.randn(self.lstm_layers, 1, self.lstm_dims)
        c0 = torch.randn(self.lstm_layers, 1, self.lstm_dims)
        return (h0, c0)

def predict_one(model, s, c2i, i2l):
    """
    Runs a sentence, s, through the model, and returns the predicted label.

    Make sure to use "torch.no_grad()"!
    See https://pytorch.org/tutorials/beginner/blitz/autograd_tutorial.html#gradients for discussion

    :param model: The LangID model to use for prediction
    :param s: The sentence to pss through, as a string
    :param c2i: The dictionary to use to map from character to index
    :param i2l: The dictionary for mapping from output index to label
    :returns: The predicted label for s
    :rtype: str
    """
    with torch.no_grad():
        output = model(vocab.sentence_to_tensor(s,c2i))
    return i2l[torch.argmax(output).item()]


def eval_acc(model, test_data, c2i, i2c, l2i, i2l):
    """
    Compute classification accuracy for the test_data against the model.

    :param model: The trained model to use
    :param test_data: A Pandas dataframe, containing a set of sentences to evaluate. Will include columns named "lang" and "sentence"
    :returns: The classification accuracy (n_correct / n_total), as well as the predictions
    :rtype: tuple(float, list(str))
    """
    acc = 0
    i = 0
    predictions = [None] * len(test_data)

    for row in test_data.itertuples():
        predictions[i] = predict_one(model, row.sentence, c2i, i2l)
        if row.lang == predictions[i]:
            acc += 1
        i += 1

    return acc / len(test_data), predictions

#####################################
# Provided utility function:
def train_model(model, n_epochs, training_data, c2i, i2c, l2i, i2l):
    """
    Train using the Adam optimizer.

    :returns: The trained model, as well as a list of average loss values from during training (for visualizing) loss stability, etc.
    """

    opt = torch.optim.Adam(model.parameters())

    # since our model gives negative log probs on the output side
    loss_func = torch.nn.NLLLoss()

    loss_batch_size = 100

    for i in range(n_epochs):

        x_train = training_data.sentence.values
        y_train = training_data.lang.values

        # There's a more pandas-ish way to do this...
        pairs = list(zip(x_train, y_train))
        random.shuffle(pairs)

        loss = 0

        for x_idx, (x, y) in enumerate(pairs):

            if x_idx % loss_batch_size == 0:
                opt.zero_grad()

            x_tens = vocab.sentence_to_tensor(x, c2i)

            y_hat = model(x_tens)

            y_tens = torch.tensor(l2i[y])

            loss += loss_func(y_hat.unsqueeze(0), y_tens.unsqueeze(0))

            if x_idx % 1000 == 0:
                print(f"{x_idx}/{len(pairs)} average per-item loss: {loss / loss_batch_size}")

            if x_idx % loss_batch_size == 0 and x_idx > 0:
                # send back gradients:
                loss.backward()
                # now, tell the optimizer to update our weights:
                opt.step()
                loss = 0

        # now one last time:
        loss.backward()
        opt.step()

    return model

def pretty_conf_matrix(conf_matrix, classes):
    """
    Make a nice matplotlib figure representing a confusion matrix, as per the Scikit-Learn Confusion Matrix demo
    """

    # for color mapping:
    norm_cm = conf_matrix.astype('float') / conf_matrix.sum(axis=1)[:, np.newaxis]

    plt.imshow(norm_cm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title('Confusion Matrix')
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45)
    plt.yticks(tick_marks, classes)

    # now label each square with the counts:
    color_thresh = norm_cm.max() / 2.
    for i, j in itertools.product(range(conf_matrix.shape[0]), range(conf_matrix.shape[1])):

        plt.text(j, i, str(conf_matrix[i,j]), horizontalalignment="center",
        color="white" if norm_cm[i,j] > color_thresh else "black")

    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.tight_layout()
