"""
Implements a ReplayStrategy mixin for generating LLM completions.

Usage:

    class MyReplayStrategy(OpenAIReplayStrategyMixin):
        ...
"""


from loguru import logger
from puterbot.strategies.base import BaseReplayStrategy
import openai import tiktoken

from puterbot import cache, config, models


# https://github.com/nalgeon/pokitoki/blob/0b6b921d367f693738e7b9bab44e6926171b48d6/bot/ai/chatgpt.py#L78
# OpenAI counts length in tokens, not characters.
# We also leave some tokens reserved for the output.
MAX_LENGTHS = {
    # max 4096 tokens total, max 3072 for the input
    "gpt-3.5-turbo": int(3 * 1024),
    # max 8192 tokens total, max 7168 for the input
    "gpt-4": int(7 * 1024),
    "gpt-4-32k": 32768,
}
MODEL_NAME = "gpt-4"

openai.api_key = config.OPENAI_API_KEY
encoding = tiktoken.get_encoding("cl100k_base")


class OpenAIReplayStrategyMixin(BaseReplayStrategy):

    def __init__(
        self,
        recording: models.Recording,
        model_name: str = config.OPENAI_MODEL_NAME,
        system_message: str = config.OPENAI_SYSTEM_MESSAGE,
    ):
        super().__init__(recording)

        logger.info(f"{model_name=}")
        self.model_name = model_name
        self.system_message = system_message

    def get_completion(
        self,
        prompt: str,
        max_tokens: int,
    ):
        messages = [
            {
                "role": "system",
                "content": self.system_message,
            },
            {
                "role": "user",
                "content": prompt,
            }
        ]
        completion = create_openai_completion(messages)
        choices = completion["choices"]
        choice = choices[0]
        message = choice["message"]
        content = message["content"]
        return content


@cache.cache()
def create_openai_completion(
    model,
    messages,
    # temperatere=1,
    # top_p=1,
    # n=1,
    # stream=False,
    # stop=None,
    # max_tokens=inf,
    # presence_penalty=0,
    # frequency_penalty=0,
    # logit_bias=None,
    # user=None,
):
    return openai.ChatCompletion.create(
        model=model,
        messages=messages,
        # temperatere=temperature,
        # top_p=top_p,
        # n=n,
        # stream=stream,
        # stop=stop,
        # max_tokens=max_tokens,
        # presence_penalty=presence_penalty,
        # frequency_penalty=frequency_penalty,
        # logit_bias=logit_bias,
        # user=user,
    )


@cache.cache()
def get_completion(
    messages,
    prompt,
    model="gpt-4",
):

    logger.info(f"{prompt=}")

    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )
    length = MAX_LENGTHS[model]
    shorten_messages(messages, length)
    logger.debug(f"messages=\n{pformat(messages)}")

    def _get_completion(
        prompt: str,
    ) -> str:
        """TODO"""

        try:
            completion = create_openai_completion(model, messages)
            logger.info(f"{completion=}")
        except openai.error.InvalidRequestError as exc:
            logger.exception(f"{exc=}")
            completion = ""

        return completion

    sleep_time = 10
    while True:
        try:
            completion = _get_completion(prompt)
        except openai.error.RateLimitError as exc:
            logger.exception(f"{exc=}")
            logger.warning(f"{sleep_time=}")
            time.sleep(sleep_time)
            sleep_time *= 2
        else:
            break
    choices = completion["choices"]
    choice = choices[0]
    message = choice["message"]
    content = message["content"]

    assistant_message = {
        "role": "assistant",
        "content": content,
    }
    logger.debug(f"appending assistant_message=\n{pformat(assistant_message)}")
    messages.append(assistant_message)
    return messages


# XXX TODO not currently in use
# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301"):
    """Returns the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        logger.info("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model == "gpt-3.5-turbo":
        logger.info(
            "Warning: gpt-3.5-turbo may change over time. Returning num tokens "
            "assuming gpt-3.5-turbo-0301."
        )
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0301")
    elif model == "gpt-4":
        logger.info(
            "Warning: gpt-4 may change over time. Returning num tokens "
            "assuming gpt-4-0314."
        )
        return num_tokens_from_messages(messages, model="gpt-4-0314")
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif model == "gpt-4-0314":
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model "
            "{model}. See "
            "https://github.com/openai/openai-python/blob/main/chatml.md for "
            information on how messages are converted to tokens.""")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens