"""Require complete, current source bindings when importing item audit proofs."""
import hashlib
from pathlib import Path


def require_inputs(proof,pdf,data,files,label):
    if proof.get('passed') is not True:raise ValueError('Failed '+label+' source proof')
    if proof.get('pdf_sha256')!=hashlib.sha256(Path(pdf).read_bytes()).hexdigest():
        raise ValueError('Stale '+label+' PDF source proof')
    inputs=proof.get('input_sha256')
    if not isinstance(inputs,dict) or set(inputs)!=set(files):
        raise ValueError('Incomplete '+label+' source proof input inventory')
    for name in files:
        if inputs[name]!=hashlib.sha256((Path(data)/name).read_bytes()).hexdigest():
            raise ValueError('Stale '+label+' source proof: '+name)
