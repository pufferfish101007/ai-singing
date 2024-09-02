from typing import NoReturn, TypeVar, List
from re import sub

def error(err: str) -> NoReturn:
  print(f'error: {err}')
  exit(1)

T = TypeVar('T')

def not_none(any: T | None) -> T:
  if any is None:
    error('none')
  return any

def s_to_ms(secs: float) -> int:
  return int(secs * 1000)

def strip_word(word: str) -> str:
 return sub(r"[^a-z]", "", word.lower())