import numpy as np
import tasks

def _canonicalize(self, data):
    x, y = data
    # remove bogus singleton dimension
    y = y.flatten()
    y[y == 10] = 0
    x_shape = np.tile([x.shape[2:]], (x.shape[0], 1))
    return (x.astype(np.float32),
            x_shape.astype(np.float32),
            y.astype(np.uint8))

class DigitTask(tasks.Classification):
    name = "svhn_digit"
    canonicalize = _canonicalize

    def __init__(self, *args, **kwargs):
        super(DigitTask, self).__init__(*args, **kwargs)
        self.n_classes = 10
        self.n_channels = 1

    def load_datasets(self):
        from fuel.datasets.svhn import SVHN
        return dict(
            train=SVHN(which_sets=["train"], which_format=2, subset=slice(None, 50000)),
            valid=SVHN(which_sets=["train"], which_format=2, subset=slice(50000, None)),
            test=SVHN(which_sets=["test"], which_format=2))

    def get_stream_num_examples(self, which_set, monitor):
        if monitor and which_set == "train":
            return 10000
        return super(DigitTask, self).get_stream_num_examples(which_set, monitor)
