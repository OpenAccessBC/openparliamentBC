import sys
import traceback
from typing import Any, override

from django.core.mail import mail_admins
from django.core.management.base import BaseCommand, CommandParser

try:
    from pudb import post_mortem
except ImportError:
    from pdb import post_mortem

from parliament import jobs


class Command(BaseCommand):
    help = "Runs a job, which is a no-arguments function in the project's jobs.py"
    args = '[job name]'

    @override
    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('jobname', type=str)
        parser.add_argument('--pdb', action='store_true', dest='pdb', help='Launch into Python debugger on exception')

    @override
    def handle(self, jobname: str, **options: Any) -> None:
        try:
            getattr(jobs, jobname)()
        except Exception as e:
            tb = ""
            try:
                if options.get('pdb'):
                    post_mortem()
                else:
                    tb = "\n".join(traceback.format_exception(*(sys.exc_info())))
                    mail_admins("Exception in job %s" % jobname,
                                "\n".join(traceback.format_exception(*(sys.exc_info()))))
            except Exception:
                print(tb)
            finally:
                raise e
