"""Módulo de modelagem e treinamento"""
from .train_model import ModelTrainer
from .lag1 import pair_consecutive_years

__all__ = ['ModelTrainer', 'pair_consecutive_years']
