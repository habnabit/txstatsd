import time

from unittest import TestCase

from txstatsd.server.processor import MessageProcessor
from txstatsd.server.configurableprocessor import ConfigurableMessageProcessor


class TestMessageProcessor(MessageProcessor):

    def __init__(self):
        super(TestMessageProcessor, self).__init__()
        self.failures = []

    def fail(self, message):
        self.failures.append(message)


class TestConfigurableMessageProcessor(ConfigurableMessageProcessor):

    def __init__(self, time_function=time.time, message_prefix=""):
        super(TestConfigurableMessageProcessor, self).__init__(
            time_function,
            message_prefix)

    def fail(self, message):
        self.failures.append(message)


class ProcessMessagesTest(TestCase):

    def setUp(self):
        self.processor = TestMessageProcessor()

    def test_receive_counter(self):
        """
        A counter message takes the format 'gorets:1|c', where 'gorets' is the
        identifier and '1' means the counter will be incremented by one
        unit. 'c' is simply used to signal that this is a counter message.
        """
        self.processor.process("gorets:1|c")
        self.assertEqual(1, len(self.processor.counter_metrics))
        self.assertEqual(1.0, self.processor.counter_metrics["gorets"])

    def test_receive_counter_rate(self):
        """
        A counter message can also take the format 'gorets:1|c|@01', where
        'gorets' is the identifier,'1' means the counter will be incremented by
        one unit and '@0.1' means the sample rate is '0.1'. Effectively, the
        counter will be multiplied by the sample rate to estimate the actual
        counter value.
        """
        self.processor.process("gorets:1|c|@0.1")
        self.assertEqual(1, len(self.processor.counter_metrics))
        self.assertEqual(10.0, self.processor.counter_metrics["gorets"])

    def test_receive_timer(self):
        """
        A timer message takes the format 'glork:320|ms', where 'glork' is the
        identifier and '320' is the time in milliseconds.
        """
        self.processor.process("glork:320|ms")
        self.assertEqual(1, len(self.processor.timer_metrics))
        self.assertEqual([320], self.processor.timer_metrics["glork"])

    def test_receive_gauge_metric(self):
        """
        A gauge metric message takes the form:
        '<name>:<count>|g'.
        'g' indicates this is a gauge metric message.
        """
        self.processor.process("gorets:9.6|g")
        self.assertEqual(1, len(self.processor.gauge_metrics))
        self.assertEqual(
            [9.6, 'gorets'],
            self.processor.gauge_metrics.pop())

    def test_receive_message_no_fields(self):
        """
        If a timer message has no fields, it is logged and discarded.
        """
        self.processor.process("glork")
        self.assertEqual(0, len(self.processor.timer_metrics))
        self.assertEqual(0, len(self.processor.counter_metrics))
        self.assertEqual(["glork"], self.processor.failures)

    def test_receive_counter_no_value(self):
        """
        If a counter message has no value, it is logged and discarded.
        """
        self.processor.process("gorets:|c")
        self.assertEqual(0, len(self.processor.counter_metrics))
        self.assertEqual(["gorets:|c"], self.processor.failures)

    def test_receive_timer_no_value(self):
        """
        If a timer message has no value, it is logged and discarded.
        """
        self.processor.process("glork:|ms")
        self.assertEqual(0, len(self.processor.timer_metrics))
        self.assertEqual(["glork:|ms"], self.processor.failures)

    def test_receive_not_enough_fields(self):
        """
        If a timer message has not enough fields, it is logged and discarded.
        """
        self.processor.process("glork:1")
        self.assertEqual(0, len(self.processor.timer_metrics))
        self.assertEqual(0, len(self.processor.counter_metrics))
        self.assertEqual(["glork:1"], self.processor.failures)

    def test_receive_too_many_fields(self):
        """
        If a timer message has too many fields, it is logged and discarded.
        """
        self.processor.process("gorets:1|c|@0.1|yay")
        self.assertEqual(0, len(self.processor.timer_metrics))
        self.assertEqual(0, len(self.processor.counter_metrics))
        self.assertEqual(["gorets:1|c|@0.1|yay"], self.processor.failures)


class FlushMessagesTest(TestCase):

    def setUp(self):
        self.processor = MessageProcessor(time_function=lambda: 42)

    def test_flush_no_stats(self):
        """
        Flushing the message processor when there are no stats available should
        still produce one message where C{statsd.numStats} is set to zero.
        """
        self.assertEqual(["statsd.numStats 0 42"], self.processor.flush())

    def test_flush_counter(self):
        """
        If a counter is present, flushing it will generate a counter message
        normalized to the default interval.
        """
        self.processor.counter_metrics["gorets"] = 42
        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        counters = messages[0].splitlines()
        self.assertEqual("stats.gorets 4 42", counters[0])
        self.assertEqual("stats_counts.gorets 42 42", counters[1])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual(0, self.processor.counter_metrics["gorets"])

    def test_flush_counter_with_empty_prefix(self):
        """
        Ensure no prefix features if none is supplied.
        """
        configurable_processor = ConfigurableMessageProcessor(
            time_function=lambda: 42)
        configurable_processor.counter_metrics["gorets"] = 42
        messages = configurable_processor.flush()
        self.assertEqual(2, len(messages))
        counters = messages[0].splitlines()
        self.assertEqual("gorets 4 42", counters[0])
        self.assertEqual("gorets 42 42", counters[1])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual(
            0, configurable_processor.counter_metrics["gorets"])

    def test_flush_counter_with_prefix(self):
        """
        Ensure the prefix features if one is supplied.
        """
        configurable_processor = ConfigurableMessageProcessor(
            time_function=lambda: 42, message_prefix="test.metric")
        configurable_processor.counter_metrics["gorets"] = 42
        messages = configurable_processor.flush()
        self.assertEqual(2, len(messages))
        counters = messages[0].splitlines()
        self.assertEqual("test.metric.gorets 4 42", counters[0])
        self.assertEqual("test.metric.gorets 42 42", counters[1])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual(
            0, configurable_processor.counter_metrics["gorets"])

    def test_flush_counter_one_second_interval(self):
        """
        It is possible to flush counters with a one-second interval, in which
        case the counter value will be unchanged.
        """
        self.processor.counter_metrics["gorets"] = 42
        messages = self.processor.flush(interval=1000)
        self.assertEqual(2, len(messages))
        counters = messages[0].splitlines()
        self.assertEqual("stats.gorets 42 42", counters[0])
        self.assertEqual("stats_counts.gorets 42 42", counters[1])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual(0, self.processor.counter_metrics["gorets"])

    def test_flush_single_timer_single_time(self):
        """
        If a single timer with a single data point is present, all of upper,
        threshold_upper, lower, mean will be set to the same value. Timer is
        reset after flush is called.
        """
        self.processor.timer_metrics["glork"] = [24]
        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        timers = messages[0].splitlines()
        self.assertEqual("stats.timers.glork.mean 24 42", timers[0])
        self.assertEqual("stats.timers.glork.upper 24 42", timers[1])
        self.assertEqual("stats.timers.glork.upper_90 24 42", timers[2])
        self.assertEqual("stats.timers.glork.lower 24 42", timers[3])
        self.assertEqual("stats.timers.glork.count 1 42", timers[4])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual([], self.processor.timer_metrics["glork"])

    def test_flush_single_timer_multiple_times(self):
        """
        If a single timer with multiple data points is present:
        - lower will be set to the smallest value
        - upper will be set to the largest value
        - upper_90 will be set to the 90th percentile
        - count will be the count of data points
        - mean will be the mean value within the 90th percentile
        """
        self.processor.timer_metrics["glork"] = [4, 8, 15, 16, 23, 42]
        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        timers = messages[0].splitlines()
        self.assertEqual("stats.timers.glork.mean 13 42", timers[0])
        self.assertEqual("stats.timers.glork.upper 42 42", timers[1])
        self.assertEqual("stats.timers.glork.upper_90 23 42", timers[2])
        self.assertEqual("stats.timers.glork.lower 4 42", timers[3])
        self.assertEqual("stats.timers.glork.count 6 42", timers[4])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual([], self.processor.timer_metrics["glork"])

    def test_flush_single_timer_50th_percentile(self):
        """
        It is possible to flush the timers with a different percentile, in this
        example, 50%.

        If a single timer with multiple data points is present:
        - lower will be set to the smallest value
        - upper will be set to the largest value
        - upper_50 will be set to the 50th percentile
        - count will be the count of data points
        - mean will be the mean value within the 50th percentile
        """
        self.processor.timer_metrics["glork"] = [4, 8, 15, 16, 23, 42]
        messages = self.processor.flush(percent=50)
        self.assertEqual(2, len(messages))
        timers = messages[0].splitlines()
        self.assertEqual("stats.timers.glork.mean 9 42", timers[0])
        self.assertEqual("stats.timers.glork.upper 42 42", timers[1])
        self.assertEqual("stats.timers.glork.upper_50 15 42", timers[2])
        self.assertEqual("stats.timers.glork.lower 4 42", timers[3])
        self.assertEqual("stats.timers.glork.count 6 42", timers[4])
        self.assertEqual("statsd.numStats 1 42", messages[1])
        self.assertEqual([], self.processor.timer_metrics["glork"])

    def test_flush_gauge_metric(self):
        """
        Test the correct rendering of the Graphite report for
        a gauge metric.
        """

        self.processor.process("gorets:9.6|g")

        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        gauge_metric = messages[0].splitlines()
        self.assertEqual(
            "stats.gauge.gorets.value 9.6 42", gauge_metric[0])
        self.assertEqual(
            "statsd.numStats 1 42", messages[1])
        self.assertEqual(0, len(self.processor.gauge_metrics))


class FlushMeterMetricMessagesTest(TestCase):

    def setUp(self):
        self.processor = MessageProcessor(time_function=self.wall_clock_time)
        self.configurable_processor = ConfigurableMessageProcessor(
            time_function=self.wall_clock_time, message_prefix="test.metric")
        self.time_now = int(time.time())

    def wall_clock_time(self):
        return self.time_now

    def mark_minutes(self, minutes):
        for i in range(1, minutes * 60, 5):
            self.processor.update_metrics()

    def test_flush_meter_metric_with_prefix(self):
        """
        Test the correct rendering of the Graphite report for
        a meter metric when a prefix is supplied.
        """
        self.configurable_processor.process("gorets:3.0|m")

        self.time_now += 1
        messages = self.configurable_processor.flush()
        self.assertEqual(2, len(messages))
        meter_metric = messages[0].splitlines()
        self.assertEqual(
            "test.metric.gorets.count 3.0 %s" % self.time_now,
            meter_metric[0])
        self.assertEqual(
            "test.metric.gorets.mean_rate 3.0 %s" % self.time_now,
            meter_metric[1])
        self.assertEqual(
            "test.metric.gorets.1min_rate 0.0 %s" % self.time_now,
            meter_metric[2])
        self.assertEqual(
            "test.metric.gorets.5min_rate 0.0 %s" % self.time_now,
            meter_metric[3])
        self.assertEqual(
            "test.metric.gorets.15min_rate 0.0 %s" % self.time_now,
            meter_metric[4])
        self.assertEqual(
            "statsd.numStats 1 %s" % self.time_now, messages[1])

    def test_flush_meter_metric(self):
        """
        Test the correct rendering of the Graphite report for
        a meter metric.
        """
        self.processor.process("gorets:3.0|m")

        self.time_now += 1
        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        meter_metric = messages[0].splitlines()
        self.assertEqual(
            "stats.meter.gorets.count 3.0 %s" % self.time_now,
            meter_metric[0])
        self.assertEqual(
            "stats.meter.gorets.mean_rate 3.0 %s" % self.time_now,
            meter_metric[1])
        self.assertEqual(
            "stats.meter.gorets.1min_rate 0.0 %s" % self.time_now,
            meter_metric[2])
        self.assertEqual(
            "stats.meter.gorets.5min_rate 0.0 %s" % self.time_now,
            meter_metric[3])
        self.assertEqual(
            "stats.meter.gorets.15min_rate 0.0 %s" % self.time_now,
            meter_metric[4])
        self.assertEqual(
            "statsd.numStats 1 %s" % self.time_now, messages[1])

        # As we are employing the expected results from test_ewma.py
        # we perform the initial tick(), before advancing the clock 60sec.
        self.processor.update_metrics()

        self.mark_minutes(1)
        self.time_now += 60
        messages = self.processor.flush()
        self.assertEqual(2, len(messages))
        meter_metric = messages[0].splitlines()
        self.assertEqual(
            "stats.meter.gorets.count 3.0 %s" % self.time_now,
            meter_metric[0])
        self.assertTrue(
            meter_metric[1].startswith(
                "stats.meter.gorets.mean_rate 0.04918032"))
        self.assertTrue(
            meter_metric[2].startswith(
                "stats.meter.gorets.1min_rate 0.22072766"))
        self.assertTrue(
            meter_metric[3].startswith(
                "stats.meter.gorets.5min_rate 0.49123845"))
        self.assertTrue(
            meter_metric[4].startswith(
                "stats.meter.gorets.15min_rate 0.5613041"))
        self.assertEqual(
            "statsd.numStats 1 %s" % self.time_now, messages[1])
