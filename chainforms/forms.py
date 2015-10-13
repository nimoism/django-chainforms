class ChainForm(object):
    def has_next_form(self):
        raise NotImplementedError()

    def get_next_form(self):
        raise NotImplementedError()
