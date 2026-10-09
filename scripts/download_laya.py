"""Explicit one-time model download. Runtime decision.py always stays offline."""
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ['HF_HOME']=str(ROOT/'models/huggingface')
os.environ['HF_HUB_OFFLINE']='0'
os.environ['TRANSFORMERS_OFFLINE']='0'
os.environ['USE_TF']='0'
os.environ['TOKENIZERS_PARALLELISM']='false'
import laya
import torch
from hyprash.decision import MODEL_ID, REVISION
torch.set_num_threads(4)
agent=laya.load(MODEL_ID,device='cpu',revision=REVISION)
print('Laya checkpoint ready for offline use:',MODEL_ID,REVISION)
