import unittest
from unittest.mock import Mock, patch
import dnb_source_worker as worker

class PublisherKeepaliveTests(unittest.TestCase):
    def setUp(self):worker._last_context_warm=0
    def test_success_warms_only_once_per_five_minutes(self):
        response=Mock();response.json.return_value={"ok":True}
        with patch.object(worker.requests,"get",return_value=response) as get:
            worker.warm_context_publisher(1000)
            worker.warm_context_publisher(1299)
            worker.warm_context_publisher(1300)
            self.assertEqual(get.call_count,2)
            self.assertEqual(get.call_args.kwargs["timeout"],15)
    def test_failure_is_retried_without_waiting_five_minutes(self):
        good=Mock();good.json.return_value={"ok":True}
        with patch.object(worker.requests,"get",side_effect=[TimeoutError(),good]) as get:
            worker.warm_context_publisher(1000)
            self.assertEqual(worker._last_context_warm,0)
            worker.warm_context_publisher(1015)
            self.assertEqual(get.call_count,2)
