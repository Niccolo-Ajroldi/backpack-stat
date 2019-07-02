import torch.nn
from ..config import CTX
from ...utils import einsum
from ..backpropextension import BackpropExtension
from ..jmp.relu import jac_mat_prod
from ..extensions import DIAG_H


class DiagHReLU(BackpropExtension):
    def __init__(self):
        super().__init__(torch.nn.ReLU, DIAG_H, req_inputs=[0])

    def apply(self, module, grad_input, grad_output):
        sqrt_h_outs = CTX._backpropagated_sqrt_h
        sqrt_h_outs_signs = CTX._backpropagated_sqrt_h_signs

        if module.input0.requires_grad:
            backpropagate_sqrt_h(module, grad_input, grad_output, sqrt_h_outs,
                                 sqrt_h_outs_signs)

    def backpropagate_sqrt_h(self, module, grad_input, grad_output,
                             sqrt_h_outs, sqrt_h_outs_signs):
        for i, sqrt_h in enumerate(sqrt_h_outs):
            sqrt_h_outs[i] = jac_mat_prod(module, grad_input, grad_output,
                                          sqrt_h)
        CTX._backpropagated_sqrt_h = sqrt_h_outs


EXTENSIONS = [DiagHReLU()]
