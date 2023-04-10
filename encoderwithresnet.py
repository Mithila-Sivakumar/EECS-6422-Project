# -*- coding: utf-8 -*-
"""EncoderwithResnet.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/12qVwHVtuaeaKBD7gnNVk6Wg2F2TpoLF9
"""

# All imports
# Link to actual code - https://github.com/ShengcaiLiao/TransMatcher/blob/main/restranmap.py
import torch
import torchvision.models as models
import torchvision.transforms as transforms
from torch import Tensor
import torch.nn as nn
from torch.nn import Module, ModuleList
import torchvision
from torch.nn.modules import TransformerEncoderLayer

"""##**Loading Backbone Networks**"""

'''
The layer3 feature map is used, with a 3×3 neck convolution appended to produce the final feature map.
The input image is resized to 384 × 128. The batch size is set to 64, with K=4 for the GS sampler.
The network is trained with the SGD optimizer, with a learning rate of 0.0005 for the backbone
network, and 0.005 for newly added layers. They are decayed by 0.1 after 10 epochs, and 15 epochs
are trained in total. Except that for RandPerson [ 36] the total number of epochs is 4, and the learning
rate step size is 2, according to the experiences in [ 36 , 17 ]. Gradient clipping is applied with T = 4
[ 17 ]. Several commonly used data augmentation methods are applied, including random flipping,
cropping, occlusion, and color jittering
'''

# Dimensions for the layers in Resnet 50 - The same used in the paper
feature_dims = {'layer2': 512, 'layer3': 1024, 'layer4': 2048}

# Resnet 50 without instance batch normalization
resnet_50 = models.resnet50(pretrained=True)

# Resnet 50 with ibn
# The reference in paper - https://github.com/XingangPan/IBN-Net
ibn_base = torch.hub.load('XingangPan/IBN-Net', 'resnet50_ibn_b', pretrained=True)

"""##**Transforms**"""

# This is the required size for resnet and IBN
transform = transforms.Compose([
     transforms.Resize(256),
     transforms.CenterCrop(224),
     transforms.ToTensor(),
     transforms.Normalize(
         mean=[0.485, 0.456, 0.406],
         std=[0.229, 0.224, 0.225]
     )
])

"""##**Encoder**"""

# From pytorch official documentation
# https://pytorch.org/docs/stable/generated/torch.nn.TransformerEncoder.html
# https://pytorch.org/tutorials/beginner/transformer_tutorial.html

class TransformerEncoder(torch.nn.Module):
    def __init__(self, encoder_layer, num_layer, norm=None):
      super(TransformerEncoder, self).__init__()
      self.layers = nn.ModuleList([copy.deepcopy(encoder_layer) for i in range(num_layer)])
      self.num_layer = num_layer
      self.norm = norm

    # Key mask extra in this TransMatcher
    # src - input sequence to the encoder src: Tensor, shape [seq_len, batch_size]
    # src_mask: Tensor, shape [seq_len, seq_len]
    # key_mask: The mask for the keys per batch
    def forward(self, src: Tensor, src_mask: Tensor, key_mask: Tensor) -> Tensor:
      out = src
      out_list = []
      for layer in self.layers:
        out = layer(out, src_mask=src_mask, key_mask=key_mask)
        out_list.append(out)
      # applying normalization to the outputs if norm is not None
      if self.norm is not None:
        for i in range(len(out_list)):
          out[i] = self.norm(out[i])
      # concatenate the outputs into 1 tensor
      output = torch.cat(out_list, dim=-1)
      return output

"""##**Resnet Class**"""

# This is where we will call the encoderlayer from pytorch
class ResnetIBN(nn.Module):
  # depth - which resnet version - I think we dont need this as we will be using only Resnet50
  # final_layer - default value is layer3 which is the third layer in resnet50
  # nhead - number of multi head attention in the encoder
  # neck - i think this is similar to d_model in Transformers which is 512
  def __init__(self, depth, ibn_type=None, final_layer='layer3', neck=512, nhead=1, num_encoder_layers=2, dim_feedforward=2048, dropout=0., pretrained=True):
    super(ResnetIBN, self).__init__()
    self.final_layer = final_layer
    self.neck = neck
    self.pretrained = pretrained
    self.base = ibn_base

    # setting the feature dimensions for layer 3 of resnet
    out_planes = feature_dims[final_layer]

    #This part i dont understand
    if neck > 0:
        self.neck_conv = nn.Conv2d(out_planes, neck, kernel_size=3, padding=1)
        out_planes = neck

    # Calling the transformer encoder of pytorch
    self.encoder = None
    if num_encoder_layers > 0:
        encoder_layer = TransformerEncoderLayer(out_planes, nhead, dim_feedforward, dropout)
        encoder_norm = None
        self.encoder = TransformerEncoder(encoder_layer, num_encoder_layers, encoder_norm)
        self.num_features = out_planes

  def forward(self, inputs):
        # passing the inputs through the backbone layer to get the feature encodings
        x = inputs
        for name, module in self.base._modules.items():
            x = module(x)
            if name == self.final_layer:
                break

        if self.neck > 0:
            x = self.neck_conv(x)

        out = x.permute(0, 2, 3, 1)  # [b, h, w, c]
        if self.encoder is not None:
            b, c, h, w = x.size()
            y = x.view(b, c, -1).permute(2, 0, 1)  # [hw, b, c]
            y = self.encoder(y)
            y = y.permute(1, 0, 2).reshape(b, h, w, -1)  # [b, h, w, c]
            out = torch.cat((out, y), dim=-1)

        return out

"""##**Main Function to test**"""

if __name__ == '__main__':
    inputs = torch.rand([64, 3, 384, 128])
    net = create('resnet50', final_layer='layer3', neck=128, num_encoder_layers=6)
    print(net)
    out = net(inputs)
    print(out.size())