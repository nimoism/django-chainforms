from formtools.wizard.storage.session import SessionStorage as FormtoolsSessionStorage

from chainforms.wizard.storage.base import BaseStorage


class SessionStorage(BaseStorage, FormtoolsSessionStorage):
    pass
