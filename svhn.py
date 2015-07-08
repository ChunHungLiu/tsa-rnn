import numpy as np

import theano
import theano.tensor as T

from blocks.initialization import Orthogonal, Constant
from blocks.bricks import MLP, Softmax, Initializable
from blocks.bricks.base import application
from blocks.filter import VariableFilter
from blocks.bricks.cost import CategoricalCrossEntropy, MisclassificationRate

from fuel.transformers import Mapping
from fuel.datasets.svhn import SVHN
from fuel.streams import DataStream
from fuel.schemes import ShuffledScheme

import util

def fix_target_representation(data):
    x, y = data
    # use zero to represent zero
    y[y == 10] = 0
    return x, y
    
class Emitter(Initializable):
    def __init__(self, hidden_dim, n_classes, **kwargs):
        super(Emitter, self).__init__(**kwargs)

        self.hidden_dim = hidden_dim
        self.n_classes = n_classes

        self.mlp = MLP(activations=[Softmax()],
                       dims=[hidden_dim, self.n_classes],
                       weights_init=Orthogonal(),
                       biases_init=Constant(0))
        self.softmax = Softmax()

        self.children = [self.mlp, self.softmax]

    # some day: @application(...) def feedback(self, h)

    @application(inputs=['h', 'y'])
    def cost(self, h, y):
        energy = self.mlp.apply(h)
        cross_entropy = util.named(self.softmax.categorical_cross_entropy(y.flatten(), energy),
                                   "cross_entropy")
        error_rate = util.named(T.neq(y.flatten(), energy.argmax(axis=1)).mean(axis=0),
                                "error_rate")
        for variable in [cross_entropy, error_rate]:
            self.add_auxiliary_variable(variable, name=variable.name)
        return cross_entropy

class DigitTask(object):
    def __init__(self, batch_size, hidden_dim, hyperparameters, shrink_dataset_by=1, **kwargs):
        self.n_classes = 10
        self.n_channels = 3
        hyperparameters["n_channels"] = self.n_channels
        self.datasets = dict(
            train=SVHN(which_sets=["train"], which_format=2, subset=slice(None, 50000)),
            valid=SVHN(which_sets=["train"], which_format=2, subset=slice(50000, None)),
            test=SVHN(which_sets=["test"], which_format=2))
        self.datastreams = dict(
            (which,
             self.get_stream(which,
                             ShuffledScheme(dataset.num_examples / shrink_dataset_by,
                                            batch_size)))
            for which, dataset in self.datasets.items())

    def get_stream(self, which_set, scheme):
        return Mapping(
            data_stream=DataStream.default_stream(
                dataset=self.datasets[which_set],
                iteration_scheme=scheme),
            mapping=fix_target_representation)

    def get_variables(self):
        # shape (batch, channel, height, width)
        x = T.tensor4('features', dtype=theano.config.floatX)
        # shape (batch_size, n_classes)
        y = T.lmatrix('targets')

        theano.config.compute_test_value = 'warn'
        x.tag.test_value = np.random.random((7, self.n_channels, 32, 32)).astype("float32")
        y.tag.test_value = np.random.random_integers(0, 9, (7, 1)).astype("int64")

        return x, y

    def get_emitter(self, hidden_dim, **kwargs):
        return Emitter(hidden_dim, self.n_classes)

    def monitor_channels(self, graph):
        return [VariableFilter(name=name)(graph.auxiliary_variables)[0]
                for name in "cross_entropy error_rate".split()]

    def plot_channels(self):
        return [["%s_%s" % (which_set, name) for which_set in self.datasets.keys()]
                for name in "cross_entropy error_rate".split()]
