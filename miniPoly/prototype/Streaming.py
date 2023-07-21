from miniPoly.prototype.prototypes import AbstractAPP


class StreamingAPP(AbstractAPP):

    def __init__(self, *args, timer_minion=None, trigger_minion=None, **kwargs):
        super(StreamingAPP, self).__init__(*args, **kwargs)

        if timer_minion is None:
            self.error(f"{self.name} could not be created because the '[timer_minion]' is not set")
            return None

        if trigger_minion is None:
            self.error(f"{self.name} could not be created because the '[trigger_minion]' is not set")
            return None

        self._param_to_compiler['timer_minion'] = timer_minion
        self._param_to_compiler['trigger_minion'] = trigger_minion
