import operator

import numpy as np

import theano
import theano.tensor as T

from blocks.filter import VariableFilter

from fuel.transformers import Mapping
from fuel.datasets.svhn import SVHN
from fuel.streams import DataStream
from fuel.schemes import ShuffledScheme

import emitters

def fix_target_representation(data):
    x, y = data
    # use zero to represent zero
    y[y == 10] = 0
    return x, y
    
class DigitTask(object):
    def __init__(self, batch_size, hidden_dim, hyperparameters, shrink_dataset_by=1, **kwargs):
        self.shrink_dataset_by = shrink_dataset_by
        self.batch_size = batch_size
        self.n_classes = 10
        self.n_channels = 3
        hyperparameters["n_channels"] = self.n_channels
        self.datasets = dict(
            train=SVHN(which_sets=["train"], which_format=2, subset=slice(None, 50000)),
            valid=SVHN(which_sets=["train"], which_format=2, subset=slice(50000, None)),
            test=SVHN(which_sets=["test"], which_format=2))

    def get_stream(self, which_set, scheme=None):
        if not scheme:
            scheme = ShuffledScheme(
                self.datasets[which_set].num_examples
                / self.shrink_dataset_by,
                self.batch_size)
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
        return emitters.SingleSoftmax(hidden_dim, self.n_classes)

    def monitor_channels(self, graph):
        return [VariableFilter(name=name)(graph.auxiliary_variables)[0]
                for name in "cross_entropy error_rate".split()]

    def plot_channels(self):
        return [["%s_%s" % (which_set, name) for which_set in self.datasets.keys()]
                for name in "cross_entropy error_rate".split()]

    def preprocess(self, x):
        print "taking mean"
        mean = 0
        n = 0
        for batch in self.get_stream("train").get_epoch_iterator(as_dict=True):
            batch_sum = batch["features"].sum(axis=0, keepdims=True)
            k = batch["features"].shape[0]
            mean = n/float(n+k) * mean + 1/float(n+k) * batch_sum
            n += k
        print "mean taken"
        return x - mean
