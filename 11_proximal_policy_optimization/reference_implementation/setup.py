#!/usr/bin/env python

from setuptools import setup

# Setup parameters
setup(name = "ppo",
      version = "0.1.0",
      description = "Proximal Policy Optimization using Gym and Keras",
      long_description = open("README.md").read(),
      packages = ["ppo"],
      author = "Dibya Chakravorty",
      author_email = "dibyachakravorty@gmail.com",
      install_requires=[
          "argparse==1.4.0",
          # There's a bug in Box2D environments like LunarLander-v2 or
          # BipedalWalker-v2 (https://github.com/openai/gym/issues/100).
          # Fix it by running the following after this package has been
          # installed:
          # pip uninstall Box2D-kengz
          # git clone https://github.com/pybox2d/pybox2d.git
          # pip install -e pybox2d
          "gym[all]==0.10.5",
          "h5py==2.7.1",
          "Keras==2.1.5",
          "scipy==1.0.1",
          # Assuming Tensorflow backend (CPU version) for Keras
          "tensorflow==2.5.0",
      ],
)
