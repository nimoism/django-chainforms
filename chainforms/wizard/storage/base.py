from formtools.wizard.storage.base import BaseStorage as FormtoolsBaseStorage


class BaseStorage(FormtoolsBaseStorage):

    def delete_step_data(self, step):
        if step in self.data[self.step_data_key]:
            del self.data[self.step_data_key][step]
