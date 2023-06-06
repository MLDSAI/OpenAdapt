"""
Implements a rudimentary mixin for using
MPT-7B to generate completions.


"""

from openadapt.strategies.base import BaseReplayStrategy
from openadapt.models import Recording
import transformers
import modal

stub = modal.Stub()

stub.cls(gpu="t4")
# We need modal, loading this model takes 12 GB 
class MPT_7BReplayStrategy(BaseReplayStrategy):

    def __init__(
        self,
        max_input_size: int,
        recording: Recording
    ):
        super.__init__(recording)

        self.model = transformers.AutoModelForCausalLM.from_pretrained(
            'mosaicml/mpt-7b',
            trust_remote_code=True
        )
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            'EleutherAI/gpt-neox-20b')

        self.max_input_size = max_input_size

    def get_completions(self, prompt: str):
        max_input_size = self.max_input_size, 2048
        if max_input_size > 2048:
            max_input_size = 2048

        prompt = prompt[-max_input_size:]
        input_tokens = self.tokenizer(prompt, return_tensors="pt")
        input_ids = input_tokens['input_ids']
        attention_mask = input_ids['attention_mask']
        # tokenizer only has these two keys in output dict.

        output = self.model.forward(input_ids=input_ids,
        attention_mask=attention_mask)

        # should I forward or just pass it in ? Can't test
        # w/o modal credz.

        loss = output.loss
        logits = output.logits

        completion = ""
        return completion

