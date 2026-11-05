"""A separate single-question worker; the loopback web server never sends external traffic."""
import argparse
from server import ROOT, ReadOnlyLabels
from ai_execution import WebAIService

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True)
    args=parser.parse_args()
    service=WebAIService(ReadOnlyLabels(),ROOT/'local_demo/runtime/forum-demo.sqlite3')
    service.run(args.job)
