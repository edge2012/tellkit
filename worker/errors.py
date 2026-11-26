"""Safe failure codes shared by the pipeline and its supervisor."""


class PipelineFailure(Exception):
    def __init__(self, code, breakdown=None):
        aliases = {'STAGE_BUDGET_EXCEEDED': 'TIMEOUT', 'EYES_TIMEOUT': 'TIMEOUT',
                   'EYES_BUDGET_EXCEEDED': 'TIMEOUT', 'JOB_NO_PROGRESS': 'TIMEOUT',
                   'ENCODING_FAILED': 'ENCODE_FAILED', 'ENCODE_DISK_FULL': 'ENCODE_FAILED',
                   'ENCODE_FONT_MISSING': 'ENCODE_FAILED', 'ENCODE_FILTER_UNSUPPORTED': 'ENCODE_FAILED',
                   'ENCODE_INVALID_DIMENSIONS': 'ENCODE_FAILED',
                   'TTS_MEASURE_TOOL_MISSING': 'TTS_AUDIO_UNMEASURABLE', 'TTS_MEASURE_FAILED': 'TTS_AUDIO_UNMEASURABLE'}
        if code in aliases:
            breakdown = dict(breakdown or {}, original_code=code)
            code = aliases[code]
        super().__init__((breakdown or {}).get('message', code) if isinstance(breakdown, dict) else code)
        from app.enforcement import AGGREGATE_CODES, reason_code, failure_presentation
        self.aggregate_code = code if code in AGGREGATE_CODES else None
        self.code = reason_code(dict(breakdown if isinstance(breakdown, dict) else {}, code=code))
        self.reason_code = self.code
        self.failure_kind = failure_presentation(self.code)['failure_kind']
        self.breakdown = breakdown

    def __reduce__(self):
        return (type(self), (self.code, self.breakdown))


def blocking_failure(hit):
    """Keep the first blocking finding intact for the internal failure receipt."""
    from copy import deepcopy
    detail = deepcopy(hit)
    measured = detail.get('measured')
    if isinstance(measured, dict):
        for key in ('scene', 'aspect', 'bbox'):
            detail.setdefault(key, measured.get(key))
        detail.setdefault('object', measured.get('object_id'))
    return PipelineFailure(hit['code'], detail)
