import logging, numbers
import theano
import util

logger = logging.getLogger(__name__)

def has_inner_graph(variable):
    return (hasattr(variable, "owner") and
            isinstance(variable.owner,
                       tuple(theano.gof.ops_with_inner_function.keys())))

# like theano.gof.graph.ancestors but descend into scan and the like
def deep_ancestors(variables):
    variables = theano.gof.graph.ancestors(variables)
    for variable in list(variables):
        try:
            inner_outputs = variable.owner.outputs
        except AttributeError:
            pass
        else:
            if has_inner_graph(variable):
                variables.extend(deep_ancestors(list(inner_outputs)))
    return variables

def graph_size(variable_list):
    return len(set(deep_ancestors(variable_list)))

def tag_with_id(variable):
    if not hasattr(variable.tag, "original_id"):
        variable.tag.original_id = id(variable)

def tag_with_ids(variables):
    list(map(tag_with_id, variables))

def shallow_clone(variable):
    if not variable.owner:
        return variable.clone()
    else:
        # clone the variable without cloning its ancestors
        i = variable.owner.outputs.index(variable)
        return variable.owner.clone().outputs[i]

def pop_transforms(variable, reason):
    try:
        transforms = variable.tag.transforms[reason]
    except (AttributeError, KeyError):
        return variable, []
    # if there are transforms to be performed, clone the variable so
    # that we can remove the transforms from it without affecting
    # other occurences of the variable. the cloned variable should be
    # passed to the transforms.
    variable = shallow_clone(variable)
    del variable.tag.transforms[reason]
    return variable, list(transforms)

def add_transform(variables, transform, reason):
    logger.warning("tagging for %s transform %s: %s"
                   % (reason, transform, variables))
    for variable in variables:
        if (not variable.owner and
            not isinstance(variable, theano.tensor.TensorConstant)):
            raise ValueError(
                """transform input variable %s and enter a world of pain. """
                """we will need to clone it to tag it as transformed, """
                """after which you will lose your reference to it. try """
                """something else.""" % variable)
        if not hasattr(variable.tag, "transforms"):
            variable.tag.transforms = dict()
        variable.tag.transforms.setdefault(reason, []).append(transform)

def apply_transforms(variables, reason, hyperparameters):
    # tag all variables with their `id` so we can determine identity
    # in the aftermath of cloning.
    tag_with_ids(deep_ancestors(variables))
    # want identical replacements for variables that were identical
    # before cloning madness.
    memory = dict()

    def fn(var):
        # get a clone that doesn't have the transforms
        var, transforms = pop_transforms(var, reason)
        for transform in transforms:
            try:
                newvar = memory[transform][var.tag.original_id]
            except KeyError:
                newvar = transform(var, **hyperparameters)
                tag_with_ids(deep_ancestors([newvar]))
                memory.setdefault(
                    transform, dict())[var.tag.original_id] = newvar
            var = newvar
        return var

    from theano.scan_module.scan_utils import map_variables
    return map_variables(fn, variables)

class DropoutTransform(object):
    def __init__(self, key, rng=None, mask=None):
        self.key = key
        self.rng = rng
        self.mask = mask

    def __str__(self):
        return ("dropout(%s%s)" % (
            self.key, ", tied_mask" if self.mask else ""))

    def __call__(self, x, rng=None, **hyperparameters):
        p = hyperparameters[self.key]
        if isinstance(p, numbers.Number) and p <= 0:
            return x
        mask = self.mask or util.get_dropout_mask(
            x.shape, p, rng=self.rng or rng)
        return x * mask

class WhiteNoiseTransform(object):
    def __init__(self, key, rng=None):
        self.key = key
        self.rng = rng

    def __str__(self):
        return "whitenoise(%s)" % self.key

    def __call__(self, x, rng, **hyperparameters):
        std = hyperparameters[self.key]
        if isinstance(std, numbers.Number) and std <= 0:
            return x
        rng = self.rng or rng
        return x + rng.normal(x.shape, std=std, dtype=x.dtype)

class ConstantTransform(object):
    def __init__(self, replacement):
        self.replacement = replacement

    def __str__(self):
        return "constant(%s)" % self.replacement

    def __call__(self, x, **hyperparameters):
        return self.replacement
