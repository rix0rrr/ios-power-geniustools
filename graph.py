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

  def max_val(self, day, event, attr):
    return max(attr.get(mmt) for mmt in self.get_all(day, event))

  def top_n(self, day, event, attrs, n):
    """Retain only the top N attributes from the given list of attributes."""
    ranks = [(self.max_val(day, event, attr), attr) for attr in attrs]
    ranks.sort(lambda a, b: int(b[0] - a[0]))
    return [x[1] for x in ranks[:n]]

  def attr_names(self, day, event):
    """Get all attr names for a given event on the given day"""
    return sorted(set(key for mmt in self.mmts
                      if mmt.time.date() == day and mmt.event == event
                      for key in mmt.attrs.keys()))

  def get_all(self, day, event):
    for mmt in self.mmts:
      if mmt.time.date() == day and mmt.event == event:
        yield mmt


mmts = Mmts()

def do_file(filename):
  for line in file(filename):
    mmts.add(Mmt.from_line(line))


class Axis(object):
  def __init__(self, label):
    self.label = label


def numberify(x, mmt):
  return float(re.sub('[^0-9.-]', '', x))


def rate(field):
  def rate_fn(x, mmt):
    x = numberify(x, mmt)
    t = numberify(mmt.attrs[field], mmt)

    return float(x) / float(t)
  return rate_fn


def active_inactive(x, mmt):
  return 1.0 if x == 'active' else 0.0


class Attr(object):
  def __init__(self, name, transform=numberify, missing=None, label=None, shape='lines smooth bezier'):
    self.name = name
    self.transform = transform
    self.missing = missing
    self.label = label or self.name
    self.shape = shape

  def get(self, mmt):
    if self.name not in mmt.attrs:
      return self.missing
    return self.transform(mmt.attrs[self.name], mmt)


plots = []

def plot(day, event, y1attrs, y1axis, y2attrs=[], y2axis=Axis(label='?'), filename=None):
  title = '%s -- %s' % (event, ', '.join(a.name for a in y1attrs + y2attrs))
  day_str = day.strftime('%Y-%m-%d')

  filename = filename or title

  y2 = """\
      set y2label "{y2label}"
      set y2tics
      """.format(y2label=y2axis.label)

  script = [textwrap.dedent("""\
      reset
      set terminal png size 800,600
      set output "{day_str} {filename}.png"

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
                 y2=y2 if y2attrs else '',
                 filename=filename))]

  script.append('plot ' + ','.join(
    ['"-" using 1:2 with %s title "%s"' % (attr.shape, attr.label) for attr in y1attrs] +
    ['"-" using 1:2 with %s title "%s" axes x1y2' % (attr.shape, attr.label) for attr in y2attrs]))

  for attr in y1attrs + y2attrs:
    for mmt in mmts.get_all(day, event):
      value = attr.get(mmt)
      if value is not None:
        script.append('%s,%s' % (mmt.time.strftime("%Y-%m-%d %H:%M:%S"), value))
    script.append('e')

  plots.append('\n'.join(script))


def make_plots(day):
  plot(day, 'Battery', [Attr('current_capacity'), Attr('raw_max_capacity')],
                       Axis(label='mAh'),
                       [Attr('current'), Attr('charging_current')],
                       Axis(label='mA'))

  plot(day, 'Battery', [Attr('level')],
                       Axis(label='%'),
                       [Attr('voltage')],
                       Axis(label='mV'))

  plot(day, 'Battery', [Attr('current'), Attr('charging_current')],
                       Axis(label='mA'),
                       [Attr('battery_temp')],
                        Axis(label='C'))

  plot(day, 'Powerstat Energy Model', [Attr('CPU Energy', transform=rate('SampleTime')),
                                       Attr('SoC Energy', transform=rate('SampleTime')),
                                       Attr('GPU Energy', transform=rate('SampleTime'))], Axis(label='mW'))

  plot(day, 'BB HW Protocol LTE', [Attr('CONNECTED', missing=0)], Axis(label='%'))
  plot(day, 'BB HW Protocol CDMA2K', [Attr('CONNECTED', missing=0)], Axis(label='%'))
  plot(day, 'BB HW Protocol 1xEVDO', [Attr('CONNECTED', missing=0)], Axis(label='%'))
  plot(day, 'BB HW Protocol GSM', [Attr('CONNECTED', missing=0)], Axis(label='%'))
  plot(day, 'BB HW Protocol WCDMA', [Attr('CONNECTED', missing=0)], Axis(label='%'))
  plot(day, 'BB HW Protocol UTRAN', [Attr('CONNECTED', missing=0)], Axis(label='%'))

  plot(day, 'CoreLocation Client', [Attr('location', transform=active_inactive, label='Active', shape='lines')],
                                   Axis(label='yes/no'))

  plot(day, 'Telephony', [Attr('signal')], Axis(label='dBm'))

  net_rate = rate('TimeSinceLastCheck')
  plot(day, 'Network Usage', [Attr('pdp_ip0_up', transform=net_rate), Attr('pdp_ip0_down', transform=net_rate),
                              Attr('pdp_ip1_up', transform=net_rate), Attr('pdp_ip1_down', transform=net_rate),
                              Attr('pdp_ip2_up', transform=net_rate), Attr('pdp_ip2_down', transform=net_rate),
                              Attr('pdp_ip3_up', transform=net_rate), Attr('pdp_ip3_down', transform=net_rate),
                              Attr('pdp_ip4_up', transform=net_rate), Attr('pdp_ip4_down', transform=net_rate),
                             ], Axis(label='bytes/sec'))

  processes = [Attr(p) for p in mmts.attr_names(day, 'ProcessMonitor')]
  top_processes = mmts.top_n(day, 'ProcessMonitor', processes, 10)
  plot(day, 'ProcessMonitor', top_processes, Axis('CPU secs (cum)'), filename='Processes')


if sys.argv[1:] == []:
  print 'Usage: graph.py FILE [...]'
  sys.exit(1)


for filename in sys.argv[1:]:
  do_file(filename)

for day in mmts.days():
  make_plots(day)

print '\n'.join(plots)
