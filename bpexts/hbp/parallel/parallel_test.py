"""
* Test Hessian backpropagation of parallel series of linear layers.
* Test splitting parameters of identical parallel layers into blocks.
"""

from torch import randn, eye
from .parallel import HBPParallel
from ..linear import HBPLinear
from ...utils import (torch_allclose,
                      set_seeds)
from ...hessian import exact


def test_splitting_into_blocks():
    """Test whether block size adaption works correctly."""
    in_features = 20
    out_features_list = [3, 2, 5]
    out_features = sum(out_features_list)

    linear = HBPLinear(in_features=in_features,
                       out_features=out_features,
                       bias=True)

    parallel = HBPParallel.from_module(linear)
    assert parallel.total_out_features() == out_features
    assert parallel.compute_out_features_list(1) == [10]
    assert parallel.compute_out_features_list(4) == [3, 3, 2, 2]
    assert parallel.compute_out_features_list(5) == [2, 2, 2, 2, 2]
    assert parallel.compute_out_features_list(6) == [2, 2, 2, 2, 1, 1]
    assert parallel.compute_out_features_list(10) == 10 * [1]
    assert parallel.compute_out_features_list(15) == 10 * [1]

    parallel2 = parallel.split(out_features_list)
    assert parallel2.total_out_features() == out_features
    assert parallel2.compute_out_features_list(1) == [10]
    assert parallel2.compute_out_features_list(4) == [3, 3, 2, 2]
    assert parallel2.compute_out_features_list(5) == [2, 2, 2, 2, 2]
    assert parallel2.compute_out_features_list(6) == [2, 2, 2, 2, 1, 1]
    assert parallel2.compute_out_features_list(10) == 10 * [1]
    assert parallel2.compute_out_features_list(15) == 10 * [1]


in_features = 20
out_features_list = [2, 3, 4]
num_layers = len(out_features_list)
input = randn(1, in_features)


def hbp_linear_with_splitting(in_features, out_features_list, bias=True):
    """Return linear layers acting in parallel on the same input.

    Parameters:
    -----------
    in_features : (int)
        Number of input features
    out_features_list : (list(int))
        Output features for each of the parallel modules
    bias : (bool)
        Use bias terms in linear layers

    Returns:
    --------
    (HBPParallel)
    """
    layers = []
    for idx, out in enumerate(out_features_list):
        layers.append(HBPLinear(in_features=in_features,
                                out_features=out,
                                bias=bias))
    return HBPParallel(layers)


def random_input():
    """Return random input copy."""
    return input.clone()


def create_layer():
    """Return example linear layer."""
    # same seed
    set_seeds(0)
    return hbp_linear_with_splitting(in_features=in_features,
                                     out_features_list=out_features_list,
                                     bias=True)


def forward(layer, input):
    """Feed input through layer and loss. Return output and loss."""
    output = layer(input)
    return output, example_loss(output)


def example_loss(tensor):
    """Test loss function. Sum over squared entries.

    The Hessian of this function with respect to its
    inputs is given by an identity matrix scaled by 2.
    """
    return (tensor**2).contiguous().view(-1).sum()


def hessian_backward():
    """Feed input through layer and loss, backward the Hessian.

    Return the layer.
    """
    layer = create_layer()
    x, loss = forward(layer, random_input())
    loss_hessian = 2 * eye(x.numel())
    loss.backward()
    # call HBP recursively
    out_h = loss_hessian
    layer.backward_hessian(out_h)
    return layer


def brute_force_hessian(layer_idx, which):
    """Compute Hessian of loss w.r.t. parameter in layer."""
    layer = create_layer()
    _, loss = forward(layer, random_input())
    if which == 'weight':
        return exact.exact_hessian(loss,
                                   [layer.get_submodule(layer_idx).weight])
    elif which == 'bias':
        return exact.exact_hessian(loss,
                                   [layer.get_submodule(layer_idx).bias])
    else:
        raise ValueError


def test_parameter_hessians(random_vp=10):
    """Test equality between HBP Hessians and brute force Hessians.
    Check Hessian-vector products."""
    # test bias Hessians
    layer = hessian_backward()
    for idx in range(num_layers):
        b_hessian = layer.get_submodule(idx).bias.hessian
        b_brute_force = brute_force_hessian(idx, 'bias')
        assert torch_allclose(b_hessian, b_brute_force, atol=1E-5)
        # check bias Hessian-veector product
        for _ in range(random_vp):
            v = randn(layer.get_submodule(idx).bias.numel())
            vp = layer.get_submodule(idx).bias.hvp(v)
            vp_result = b_brute_force.matmul(v)
            assert torch_allclose(vp, vp_result, atol=1E-5)
    # test weight Hessians
    for idx in range(num_layers):
        w_hessian = layer.get_submodule(idx).weight.hessian()
        w_brute_force = brute_force_hessian(idx, 'weight')
        assert torch_allclose(w_hessian, w_brute_force, atol=1E-5)
        # check weight Hessian-vector product
        for _ in range(random_vp):
            v = randn(layer.get_submodule(idx).weight.numel())
            vp = layer.get_submodule(idx).weight.hvp(v)
            vp_result = w_brute_force.matmul(v)
            assert torch_allclose(vp, vp_result, atol=1E-5)


def brute_force_input_hessian():
    """Compute the Hessian with respect to the input by brute force."""
    layer = create_layer()
    input = random_input()
    input.requires_grad = True
    _, loss = forward(layer, input)
    return exact.exact_hessian(loss, [input])


def test_input_hessians():
    """Test whether Hessian with respect to input is correctly reproduced."""
    layer = create_layer()
    out, loss = forward(layer, random_input())
    loss_hessian = 2 * eye(out.numel())
    loss.backward()
    # call HBP recursively
    in_h = layer.backward_hessian(loss_hessian)
    assert torch_allclose(in_h, brute_force_input_hessian())
