import datetime
import json
import os

from moto import mock_dynamodb2
import pytest

import lambda_function.function as function_code
from mocks import dynamodb_mocks
from mocks import Context


def test_handler():
    assert False is True
