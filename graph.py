import collections
import datetime
import re
import string
import sys
import textwrap


class Mmt(object):
  def __init__(self, time, event, attrs):
    self.time = time
    self.event = event
    self.attrs = attrs

  @staticmethod
  def from_line(line):
    m = re.match('^(.+?)\[([^\]]+)\](.*)$', line)
    if not m:
      return None

    time = datetime.datetime.strptime(m.group(1).strip(), '%m/%d/%y %H:%M:%S')
    event = m.group(2)

    clauses = m.group(3).strip().split(';')
    try:
      attrs = dict(map(string.strip, clause.split('=', 2)) for clause in clauses if clause)

      return Mmt(time, event, attrs)
    except ValueError:
      return None


class Mmts(object):
  def __init__(self):
    self.mmts = []

  def add(self, mmt):
    if mmt:
      self.mmts.append(mmt)

  def days(self):
    return set(mmt.time.date() for mmt in self.mmts)

  def get_all(self, day, event, attr):
    for mmt in self.mmts:
      if mmt.time.date() == day and mmt.event == event and attr in mmt.attrs:
        yield mmt


mmts = Mmts()

def do_file(filename):
  for line in file(filename):
    mmts.add(Mmt.from_line(line))


class Axis(collections.namedtuple('Axis', ['label'])):
  def __new__(cls, label):
    return super(Axis, cls).__new__(cls, label)


def numberify(x):
  return re.sub('[^0-9.-]', '', x)


plots = []

def plot(day, event, y1attrs, y1axis, y2attrs=[], y2axis=Axis(label='?')):
  title = '%s -- %s' % (event, ', '.join(y1attrs + y2attrs))

  day_str = day.strftime('%Y-%m-%d')

  y2 = textwrap.dedent("""\
      set y2label "{y2label}"
      set y2tics
      """.format(y2label=y2axis.label))

  script = [textwrap.dedent("""\
      reset
      set terminal png size 800,600
      set output "{day_str} {title}.png"

      set xdata time
      set timefmt "%Y-%m-%d %H:%M:%S"
      set format x "%H:%M"
      set xlabel "Time"

      set autoscale

      set ylabel "{ylabel}"
      {y2}

      set title "{title}"
      set key below
      set grid

      set datafile separator ","
      """.format(ylabel=y1axis.label,
                 title=title,
                 day_str=day_str,
                 y2=y2 if y2attrs else ''))]

  script.append('plot ' + ','.join(
    ['"-" using 1:2 with lines title "%s" smooth bezier' % attr for attr in y1attrs] +
    ['"-" using 1:2 with lines title "%s" smooth bezier axes x1y2' % attr for attr in y2attrs]))

  for attr in y1attrs + y2attrs:
    for mmt in mmts.get_all(day, event, attr):
      script.append('%s,%s' % (mmt.time.strftime("%Y-%m-%d %H:%M:%S"), numberify(mmt.attrs[attr])))
    script.append('e')

  plots.append('\n'.join(script))


def make_plots(day):
  plot(day, 'Battery', ['current_capacity', 'raw_max_capacity'], Axis(label='mAh'),
                       ['current', 'charging_current'], Axis(label='mA'))
  plot(day, 'Battery', ['level'], Axis(label='%'),
                       ['voltage'], Axis(label='mV'))
  plot(day, 'Battery', ['current', 'charging_current'], Axis(label='mA'),
                       ['battery_temp'], Axis(label='C'))

  plot(day, 'Powerstat Energy Model', ['CPU Energy', 'SoC Energy', 'GPU Energy'], Axis(label='mJ'))


if sys.argv[1:] == []:
  print 'Usage: graph.py FILE [...]'
  sys.exit(1)


for filename in sys.argv[1:]:
  do_file(filename)

for day in mmts.days():
  make_plots(day)

print '\n'.join(plots)
