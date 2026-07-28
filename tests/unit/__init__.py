#python -m pytest tests/unit/ -v                                  #名 each test
#python -m pytest tests/unit/test_agent1_duplicate_guard.py -q    # one file
#python -m pytest tests/unit/ -q -k "guard"                       # match by name
#python -m pytest tests/unit/ -q -x                               # stop at first failure