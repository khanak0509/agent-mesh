from typing import Optional, Type, TypeVar

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent_shared.config import settings

T = TypeVar("T", bound=BaseModel)


def make_llm(model: Optional[str] = None, temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.default_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
    )


def generate(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    llm = make_llm(model=model)
    messages = []
    if system:
        messages.append(("system", system))
    messages.append(("human", "{input}"))
    chain = ChatPromptTemplate.from_messages(messages) | llm | StrOutputParser()
    return chain.invoke({"input": prompt})


def generate_structured(
    prompt: str,
    schema: Type[T],
    system: Optional[str] = None,
    model: Optional[str] = None,
) -> T:
    llm = make_llm(model=model, temperature=0.2)
    structured = llm.with_structured_output(schema)
    messages = []
    if system:
        messages.append(("system", system))
    messages.append(("human", "{input}"))
    chain = ChatPromptTemplate.from_messages(messages) | structured
    return chain.invoke({"input": prompt})


def build_chain(system: str, model: Optional[str] = None, temperature: float = 0.3):
    llm = make_llm(model=model, temperature=temperature)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "{input}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def build_structured_chain(
    system: str,
    schema: Type[T],
    model: Optional[str] = None,
):
    llm = make_llm(model=model, temperature=0.2)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "{input}"),
        ]
    )
    return prompt | llm.with_structured_output(schema)
