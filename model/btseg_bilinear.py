import torch
import torch.nn as nn

class ResNetBlock(nn.Module):
    def __init__(self, channels):
        super(ResNetBlock, self).__init__()
        # 1. using 32 groups which is the default from GN paper
        #
        # 2. nn.ReLU() creates an nn.Module which you can add e.g.
        # to an nn.Sequential model. nn.functional.relu on the
        # other side is just the functional API call to the relu
        # function, so that you can add it e.g. in your forward
        # method yourself.
        #
        # Generally speaking it might depend on your coding style
        # if you prefer modules for the activations or the functional calls.
        # Personally I prefer the module approach if the activation has an
        # internal state, e.g. PReLU.
        #
        self.feats = nn.Sequential(nn.GroupNorm(32, channels),
                                   nn.ReLU(inplace=True),
                                   nn.Conv3d(channels, channels,
                                       kernel_size=3, stride=1, padding=1),
                                   nn.GroupNorm(32, channels),
                                   nn.ReLU(inplace=True),
                                   nn.Conv3d(channels, channels,
                                       kernel_size=3, stride=1, padding=1))

    def forward(self, x):
        residual = x
        out = self.feats(residual)
        out += residual
        return out


class DownSampling(nn.Module):
    # downsample by 2; simultaneously increase feature size by 2
    def __init__(self, channels):
        super(DownSampling, self).__init__()
        self.conv3x3x3 = nn.Conv3d(channels, 2*channels,
                kernel_size=3, stride=2, padding=1)

    def forward(self, x):
        return self.conv3x3x3(x)


# "Each decoder level begins with upsizing: reducing the number
# of features by a factor of 2 (using 1x1x1 convolutions) and doubling the spatial
# dimension (using 3D bilinear upsampling), followed by an addition of encoder
# output of the equivalent spatial level."
class UpsamplingBilinear3d(nn.modules.Upsample):
    def __init__(self, size=None, scale_factor=2):
        super(UpsamplingBilinear3d, self).__init__(size, scale_factor,
						mode='trilinear', align_corners=True)

# Taken from: https://github.com/pytorch/pytorch/issues/12207#issuecomment-504729632
# Maybe adapt?
#class UpsampleDeterministic(nn.Module):
#    def __init__(self,upscale=2):
#        super(UpsampleDeterministic, self).__init__()
#        self.upscale = upscale
#
#    def forward(self, x):
#        '''
#        x: 4-dim tensor. shape is (batch,channel,h,w)
#        output: 4-dim tensor. shape is (batch,channel,self.upscale*h,self.upscale*w)
#        '''
#        return x[:, :, :, None, :, None].expand(-1, -1, -1, self.upscale, -1, self.upscale)
#	 .reshape(x.size(0), x.size(1), x.size(2)*self.upscale, x.size(3)*self.upscale)
#

class CompressFeatures(nn.Module):
    # Reduce the number of features by a factor of 2.
    # Assumes channels_in is power of 2.
    def __init__(self, channels_in, channels_out):
        super(CompressFeatures, self).__init__()
        self.conv1x1x1 = nn.Conv3d(channels_in, channels_out,
                kernel_size=1, stride=1, padding=0)

    def forward(self, x):
        return self.conv1x1x1(x)



class UpsamplingDeconv3d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=4):
        super(UpsamplingDeconv3d, self).__init__()
        self.deconv = torch.nn.ConvTranspose3d(in_channels,
                                               out_channels,
                                               kernel_size,
                                                stride=2,
                                                padding=1,
                                                output_padding=0,
                                                groups=1,
                                                bias=True,
                                                dilation=1,
                                                padding_mode='zeros')
    def forward(self, x):
        return self.deconv(x)

class BraTSSegmentation(nn.Module):
    def __init__(self, input_channels=4, output_channels=3):
        super(BraTSSegmentation, self).__init__()
        # channels_in=4, channels_out=32
        self.up = UpsamplingBilinear3d()
        self.sig = nn.Sigmoid()
        self.initConv = nn.Conv3d(input_channels, 32, kernel_size=3, stride=1, padding=1)
        self.block0 = ResNetBlock(32)
        self.ds1 = DownSampling(32)
        self.block1 = ResNetBlock(64)
        self.block2 = ResNetBlock(64)
        self.ds2 = DownSampling(64)
        self.block3 = ResNetBlock(128)
        self.block4 = ResNetBlock(128)
        self.ds3 = DownSampling(128)
        self.block5 = ResNetBlock(256)
        self.block6 = ResNetBlock(256)
        self.block7 = ResNetBlock(256)
        self.block8 = ResNetBlock(256)
        self.cf1 = CompressFeatures(256, 128)
        self.block9 = ResNetBlock(128)
        self.cf2 = CompressFeatures(128, 64)
        self.block10 = ResNetBlock(64)
        self.cf3 = CompressFeatures(64, 32)
        self.block11 = ResNetBlock(32)
        self.cf_final = CompressFeatures(32, output_channels)

        self.up1 = UpsamplingDeconv3d(32, 32)
        self.up2 = UpsamplingDeconv3d(64, 64)
        self.up3 = UpsamplingDeconv3d(128, 128)


    def forward(self, x):
        # sp* is the state of the output at each spatial level
        sp0 = self.initConv(x)
        sp1 = self.block0(sp0)
        sp2 = self.ds1(sp1)
        sp2 = self.block1(sp2)
        sp2 = self.block2(sp2)
        sp3 = self.ds2(sp2)
        sp3 = self.block3(sp3)
        sp3 = self.block4(sp3)
        sp4 = self.ds3(sp3)
        sp4 = self.block5(sp4)
        sp4 = self.block6(sp4)
        sp4 = self.block7(sp4)
        sp4 = self.block8(sp4)

        sp3 = sp3 + self.up(self.cf1(sp4))
        sp3 = self.block9(sp3)
        sp2 = sp2 + self.up(self.cf2(sp3))
        sp2 = self.block10(sp2)
        sp1 = sp1 + self.up(self.cf3(sp2))

        sp1 = self.block11(sp1)
        output = self.sig(self.cf_final(sp1))

        return output










