#!/usr/bin/python

import matplotlib; matplotlib.use('Agg') # for systems without X11
from matplotlib.backends.backend_pdf import PdfPages
import sys, os, argparse, subprocess, json, pylab, numpy
from itertools import cycle
from re import search

"""
python parse-shadow.py --help
"""

download_medians = []
download_means = []
total_throughput = []

pylab.rcParams.update({
    'backend': 'PDF',
    'font.size': 16,
    'figure.figsize': (6,4.5),
    'figure.dpi': 100.0,
    'figure.subplot.left': 0.15,
    'figure.subplot.right': 0.95,
    'figure.subplot.bottom': 0.15,
    'figure.subplot.top': 0.95,
    'grid.color': '0.1',
    'axes.grid' : True,
    'axes.titlesize' : 'small',
    'axes.labelsize' : 'small',
    'axes.formatter.limits': (-4,4),
    'axes.spines.top': False,
    'axes.spines.right': False,
    'xtick.major.width' : 0,
    'ytick.major.width' : 0,
    'xtick.labelsize' : 'small',
    'ytick.labelsize' : 'small',
    'lines.linewidth' : 2.0,
    'lines.markeredgewidth' : 0.5,
    'lines.markersize' : 10,
    'legend.fontsize' : 'x-small',
    'legend.fancybox' : False,
    'legend.shadow' : False,
    'legend.edgecolor' : 'none',
    'legend.borderaxespad' : 0.5,
    'legend.numpoints' : 1,
    'legend.handletextpad' : 0.5,
    'legend.handlelength' : 1.6,
    'legend.labelspacing' : .75,
    'legend.markerscale' : 1.0,
    # turn on the following to embedd fonts; requires latex
    #'ps.useafm' : True,
    #'pdf.use14corefonts' : True,
    #'text.usetex' : True,
})

try: pylab.rcParams.update({'figure.max_num_figures':50})
except: pylab.rcParams.update({'figure.max_open_warning':50})
try: pylab.rcParams.update({'legend.ncol':1.0})
except: pass

LINEFORMATS="k-,r-,b-,g-,c-,m-,y-,k--,r--,b--,g--,c--,m--,y--,k:,r:,b:,g:,c:,m:,y:,k-.,r-.,b-.,g-.,c-., m-.,y-."

# a custom action for passing in experimental data directories when plotting
class PlotDataAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # extract the path to our data, and the label for the legend
        datapath = os.path.abspath(os.path.expanduser(values[0]))
        label = values[1]
        # check the path exists
        if not os.path.exists(datapath): raise argparse.ArgumentError(self, "The supplied path to the plot data does not exist: '{0}'".format(datapath))
        # remove the default
        if "_didremovedefault" not in namespace:
            setattr(namespace, self.dest, [])
            setattr(namespace, "_didremovedefault", True)
        # append out new experiment path
        dest = getattr(namespace, self.dest)
        dest.append((datapath, label))

def main():
    parser = argparse.ArgumentParser(
        description='Utility to help plot results from the Shadow simulator',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-d', '--data',
        help="""Append a PATH to the directory containing the xz-compressed
                tor.throughput.json.xz and filetransfer.downloads.json.xz,
                and the LABEL we should use for the graph legend for this
                set of experimental results""",
        metavar=("PATH", "LABEL"),
        nargs=2,
        required="True",
        action=PlotDataAction, dest="experiments")

    parser.add_argument('-c', '--config',
        help="a PATH to a shadow.config.xml file",
        metavar="PATH", type=type_str_path_in,
        action="store", dest="shadow_config",
        default=None)

    parser.add_argument('-p', '--prefix',
        help="a STRING filename prefix for graphs we generate",
        metavar="STRING",
        action="store", dest="prefix",
        default=None)

    parser.add_argument('-f', '--format',
        help="""A comma-separated LIST of color/line format strings to cycle to
                matplotlib's plot command (see matplotlib.pyplot.plot)""",
        metavar="LIST",
        action="store", dest="lineformats",
        default=LINEFORMATS)

    parser.add_argument('-s', '--skip',
        help="""Ignore the first N seconds of each log file while parsing""",
        metavar="N",
        action="store", dest="skiptime", type=type_nonnegative_integer,
        default=0)

    parser.add_argument('-r', '--rskip',
        help="""Ignore everything after N seconds of each log file while parsing""",
        metavar="N",
        action="store", dest="rskiptime", type=type_nonnegative_integer,
        default=0)

    parser.add_argument('-e', '--host-exp-all',
        help="""Set the regex PATTERN that is used with re.search to filter
                by hostname the data used in all generated plots. If set,
                this option overrides all other host expression options,
                and replaces the value of all host expressions with the
                value set here.""",
        action="store", dest="hostpatternall",
        metavar="PATTERN",
        default=None)

    parser.add_argument('--host-exp-shadow',
        help="""Set the regex PATTERN that is used with re.search to filter
                by hostname the data used in generated Shadow plots""",
        action="store", dest="hostpatternshadow",
        metavar="PATTERN",
        default=".*")

    parser.add_argument('--host-exp-tgen',
        help="""Set the regex PATTERN that is used with re.search to filter
                by hostname the data used in generated TGen plots""",
        action="store", dest="hostpatterntgen",
        metavar="PATTERN",
        default="client")

    parser.add_argument('--host-exp-tor',
        help="""Set the regex PATTERN that is used with re.search to filter
                by hostname the data used in generated Tor plots""",
        action="store", dest="hostpatterntor",
        metavar="PATTERN",
        default="^(relay|4uthority)")

    parser.add_argument('--host-exp-payment',
        help="""Set the regex PATTERN that is used with re.search to filter
                by hostname the data used in generated Payment plots""",
        action="store", dest="hostpatternpayment",
        metavar="PATTERN",
        default="")

    parser.add_argument('--no-title',
        help="""Plot all graphs without a title""",
        action="store_true", dest="notitle", default=0)

    parser.add_argument('--graph-origin',
        help="""Plot all graphs with the scale set to include the origin""",
        action="store_true", dest="graphorigin", default=0)


    args = parser.parse_args()
    conf = args.shadow_config

    if args.hostpatternall is not None:
        args.hostpatternshadow = args.hostpatternall
        args.hostpatterntgen = args.hostpatternall
        args.hostpatterntor = args.hostpatternall
        args.hostpatternpayment = args.hostpatternall

    tickdata, shdata, ftdata, tgendata, tordata, paymentdata = get_data(args.experiments, args.lineformats, args.skiptime, args.rskiptime, args.hostpatternshadow, args.hostpatterntgen, args.hostpatterntor, args.hostpatternpayment)

    page = PdfPages("{0}shadow.results.pdf".format(args.prefix+'.' if args.prefix is not None else ''))
    info = open("{0}shadow.info.txt".format(args.prefix+'.' if args.prefix is not None else ''), 'wb')
    # use a try block in case there are errors, the PDF will still be openable
    try:
        if len(tickdata) > 0:
            plot_shadow_time(tickdata, page, args)
            plot_shadow_ram(tickdata, page, args)
        if len(shdata) > 0:
            plot_shadow_packets(shdata, page, args, direction="recv")
            plot_shadow_packets(shdata, page, args, direction="send")
        if len(ftdata) > 0:
            plot_filetransfer_firstbyte(ftdata, page, args)
            plot_filetransfer_lastbyte_all(ftdata, page, args)
            plot_filetransfer_lastbyte_median(ftdata, page, args)
            plot_filetransfer_lastbyte_mean(ftdata, page, args)
            plot_filetransfer_lastbyte_max(ftdata, page, args)
            plot_filetransfer_downloads(ftdata, page, args)
        if len(tgendata) > 0:
            plot_tgen_throughput(tgendata, page, args)
            plot_tgen_firstbyte(tgendata, page, args)
            plot_tgen_lastbyte_all(tgendata, page, info, args)
            plot_tgen_lastbyte_median(tgendata, page, args)
            plot_tgen_lastbyte_mean(tgendata, page, args)
            plot_tgen_lastbyte_max(tgendata, page, args)
            plot_tgen_downloads(tgendata, page, args)
            plot_tgen_errors(tgendata, page, args)
            plot_tgen_errsizes_all(tgendata, page, args)
            plot_tgen_errsizes_median(tgendata, page, args)
            plot_tgen_errsizes_mean(tgendata, page, args)
        if len(tordata) > 0:
            capacities = get_relay_capacities(conf, bwdown=True) if conf is not None else None
            plot_tor(tordata, page, args, capacities=capacities, direction="bytes_read")
            capacities = get_relay_capacities(conf, bwup=True) if conf is not None else None
            plot_tor(tordata, page, args, capacities=capacities, direction="bytes_written")
        if len(paymentdata) > 0:
            plot_payment_numpayments(paymentdata, page, args)
            plot_payment_lifetime(paymentdata, page, args)
            plot_payment_ttestablish(paymentdata, page, args)
            plot_payment_ttpayment(paymentdata, page, args)
            plot_payment_ttpaysuccess(paymentdata, page, args)
            plot_payment_ttclose(paymentdata, page, args)
            plot_payment_payment_efficiency(paymentdata, page, args)
            plot_payment_traffic(paymentdata, info, args)
    except:
        page.close()
        info.close()
        print >>sys.stderr, "!! there was an error while plotting, but some graphs may still be readable"
        raise
    page.close()
    info.close()

def plot_shadow_time(datasource, page, args):
    pylab.figure()

    for (d, label, lineformat) in datasource:
        data = {}
        for k in d.keys(): data[int(k)] = float(d[k]['time_seconds'])/3600.0
        x = sorted(data.keys())
        y = [data[k] for k in x]
        pylab.plot(x, y, lineformat, label=label)

    pylab.xlabel("Tick (s)")
    pylab.ylabel("Real Time (h)")
    if not args.notitle: pylab.title("simulation run time")
    pylab.legend(loc="upper left")
    page.savefig()
    pylab.close()

def plot_shadow_ram(datasource, page, args):
    pylab.figure()

    for (d, label, lineformat) in datasource:
        data = {}
        for k in d.keys(): data[int(k)] = float(d[k]['maxrss_gib'])
        x = sorted(data.keys())
        y = [data[k] for k in x]
        pylab.plot(x, y, lineformat, label=label)

    pylab.xlabel("Tick (s)")
    pylab.ylabel("Maximum Resident Set Size (GiB)")
    if not args.notitle: pylab.title("simulation memory usage")
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()

def plot_shadow_packets(datasource, page, args, direction="send"):
    total_all_mafig, total_all_cdffig, total_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    data_all_mafig, data_all_cdffig, data_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    control_all_mafig, control_all_cdffig, control_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    retrans_all_mafig, retrans_all_cdffig, retrans_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    fracdata_all_mafig, fracdata_all_cdffig, fracdata_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    fraccontrol_all_mafig, fraccontrol_all_cdffig, fraccontrol_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()
    fracretrans_all_mafig, fracretrans_all_cdffig, fracretrans_each_cdffig = pylab.figure(), pylab.figure(), pylab.figure()

    for (d, label, lineformat) in datasource:
        total_all, data_all, control_all, retrans_all = {}, {}, {}, {}
        total_each, data_each, control_each, retrans_each = [], [], [], []
        fracdata_all, fraccontrol_all, fracretrans_all = {}, {}, {}
        fracdata_each, fraccontrol_each, fracretrans_each = [], [], []

        for node in d:
            for tstr in d[node][direction]['bytes_total']:
                totalmib = d[node][direction]['bytes_total'][tstr]/1048576.0
                datamib = d[node][direction]['bytes_data_payload'][tstr]/1048576.0
                controlmib = (d[node][direction]['bytes_control_header'][tstr]+d[node][direction]['bytes_control_header_retrans'][tstr]+d[node][direction]['bytes_data_header'][tstr]+d[node][direction]['bytes_data_header_retrans'][tstr])/1048576.0
                retransmib = (d[node][direction]['bytes_control_header_retrans'][tstr]+d[node][direction]['bytes_data_header_retrans'][tstr]+d[node][direction]['bytes_data_payload_retrans'][tstr])/1048576.0

                t = int(tstr)
                for datadict in [total_all, data_all, control_all, retrans_all]:
                    if t not in datadict: datadict[t] = 0.0

                total_all[t] += totalmib
                data_all[t] += datamib
                control_all[t] += controlmib
                retrans_all[t] += retransmib

                total_each.append(totalmib)
                data_each.append(datamib)
                control_each.append(controlmib)
                retrans_each.append(retransmib)

                datafrac = 0.0 if totalmib == 0.0 else datamib/totalmib
                controlfrac = 0.0 if totalmib == 0.0 else controlmib/totalmib
                retransfrac = 0.0 if totalmib == 0.0 else retransmib/totalmib

                fracdata_each.append(datafrac)
                fraccontrol_each.append(controlfrac)
                fracretrans_each.append(retransfrac)

        for t in total_all:
            if total_all[t] == 0.0: fracdata_all[t], fraccontrol_all[t], fracretrans_all[t] = 0.0, 0.0, 0.0
            else: fracdata_all[t], fraccontrol_all[t], fracretrans_all[t] = data_all[t]/total_all[t], control_all[t]/total_all[t], retrans_all[t]/total_all[t]

        ## TOTAL
        pylab.figure(total_all_mafig.number)
        x = sorted(total_all.keys())
        y = [total_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(total_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(total_each_cdffig.number)
        x, y = getcdf(total_each)
        pylab.plot(x, y, lineformat, label=label)

        ## PAYLOAD (not retrans)
        pylab.figure(data_all_mafig.number)
        x = sorted(data_all.keys())
        y = [data_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(data_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(data_each_cdffig.number)
        x, y = getcdf(data_each)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fracdata_all_mafig.number)
        x = sorted(fracdata_all.keys())
        y = [fracdata_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(fracdata_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fracdata_each_cdffig.number)
        x, y = getcdf(fracdata_each)
        pylab.plot(x, y, lineformat, label=label)

        ## CONTROL and DATA HEADERS (including retrans)
        pylab.figure(control_all_mafig.number)
        x = sorted(control_all.keys())
        y = [control_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(control_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(control_each_cdffig.number)
        x, y = getcdf(control_each)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fraccontrol_all_mafig.number)
        x = sorted(fraccontrol_all.keys())
        y = [fraccontrol_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(fraccontrol_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fraccontrol_each_cdffig.number)
        x, y = getcdf(fracdata_each)
        pylab.plot(x, y, lineformat, label=label)

        ## RETRANSMIT HEADER AND PAYLOAD
        pylab.figure(retrans_all_mafig.number)
        x = sorted(retrans_all.keys())
        y = [retrans_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(retrans_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(retrans_each_cdffig.number)
        x, y = getcdf(retrans_each)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fracretrans_all_mafig.number)
        x = sorted(fracretrans_all.keys())
        y = [fracretrans_all[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1, edgecolor=lineformat[0])
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(fracretrans_all_cdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(fracretrans_each_cdffig.number)
        x, y = getcdf(fracretrans_each)
        pylab.plot(x, y, lineformat, label=label)

    pylab.figure(total_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Throughput (MiB/s)")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average throughput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(total_all_mafig)

    pylab.figure(total_all_cdffig.number)
    pylab.xlabel("Throughput (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second throughput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(total_all_cdffig)

    pylab.figure(total_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Throughput (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second throughput, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(total_each_cdffig)

    pylab.figure(data_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Goodput (MiB/s)")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average goodput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(data_all_mafig)

    pylab.figure(data_all_cdffig.number)
    pylab.xlabel("Goodput (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second goodput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(data_all_cdffig)

    pylab.figure(data_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Goodput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second goodput, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(data_each_cdffig)

    pylab.figure(fracdata_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Goodput / Throughput")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average fractional goodput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracdata_all_mafig)

    pylab.figure(fracdata_all_cdffig.number)
    pylab.xlabel("Goodput / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional goodput, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracdata_all_cdffig)

    pylab.figure(fracdata_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Goodput / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional goodput, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracdata_each_cdffig)

    pylab.figure(control_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Control Overhead (MiB/s)")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average control overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(control_all_mafig)

    pylab.figure(control_all_cdffig.number)
    pylab.xlabel("Control Overhead (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second control overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(control_all_cdffig)

    pylab.figure(control_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Control Overhead")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second control overhead, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(control_each_cdffig)

    pylab.figure(fraccontrol_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Control Overhead / Throughput")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average fractional control overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fraccontrol_all_mafig)

    pylab.figure(fraccontrol_all_cdffig.number)
    pylab.xlabel("Control Overhead / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional control overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fraccontrol_all_cdffig)

    pylab.figure(fraccontrol_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Control Overhead / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional control overhead, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fraccontrol_each_cdffig)

    pylab.figure(retrans_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Retransmission Overhead (MiB/s)")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average retrans overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(retrans_all_mafig)

    pylab.figure(retrans_all_cdffig.number)
    pylab.xlabel("Retransmission Overhead (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second retrans overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(retrans_all_cdffig)

    pylab.figure(retrans_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Retransmission Overhead")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second retrans overhead, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(retrans_each_cdffig)

    pylab.figure(fracretrans_all_mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Retransmission Overhead / Throughput")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average fractional retrans overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracretrans_all_mafig)

    pylab.figure(fracretrans_all_cdffig.number)
    pylab.xlabel("Retransmission Overhead / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional retrans overhead, {0}, all nodes".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracretrans_all_cdffig)

    pylab.figure(fracretrans_each_cdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Retransmission Overhead / Throughput")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second fractional retrans overhead, {0}, each node".format(direction))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(fracretrans_each_cdffig)

def plot_filetransfer_firstbyte(data, page, args):
    pylab.figure()

    for (d, label, lineformat) in data:
        fb = []
        for client in d:
            for bytes in d[client]:
                client_fb_list = d[client][bytes]["firstbyte"]
                for sec in client_fb_list: fb.append(sec)
        x, y = getcdf(fb)
        pylab.plot(x, y, lineformat, label=label)

    pylab.xlabel("Download Time (s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("time to download first byte, all clients")
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()

def plot_filetransfer_lastbyte_all(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            for b in d[client]:
                bytes = int(b)
                if bytes not in figs: figs[bytes] = pylab.figure()
                if bytes not in lb: lb[bytes] = []
                client_lb_list = d[client][b]["lastbyte"]
                for sec in client_lb_list: lb[bytes].append(sec)
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to download {0} bytes, all downloads".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_filetransfer_lastbyte_median(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            for b in d[client]:
                bytes = int(b)
                if bytes not in figs: figs[bytes] = pylab.figure()
                if bytes not in lb: lb[bytes] = []
                client_lb_list = d[client][b]["lastbyte"]
                if len(client_lb_list) > 0: lb[bytes].append(numpy.median(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("median time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_filetransfer_lastbyte_mean(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            for b in d[client]:
                bytes = int(b)
                if bytes not in figs: figs[bytes] = pylab.figure()
                if bytes not in lb: lb[bytes] = []
                client_lb_list = d[client][b]["lastbyte"]
                if len(client_lb_list) > 0: lb[bytes].append(numpy.mean(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("mean time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_filetransfer_lastbyte_max(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            for b in d[client]:
                bytes = int(b)
                if bytes not in figs: figs[bytes] = pylab.figure()
                if bytes not in lb: lb[bytes] = []
                client_lb_list = d[client][b]["lastbyte"]
                if len(client_lb_list) > 0: lb[bytes].append(numpy.max(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("max time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_filetransfer_downloads(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        dls = {}
        for client in d:
            for bytes in d[client]:
                if bytes not in figs: figs[bytes] = pylab.figure()
                if bytes not in dls: dls[bytes] = {}
                if client not in dls[bytes]: dls[bytes][client] = 0
                client_lb_list = d[client][bytes]["lastbyte"]
                for sec in client_lb_list: dls[bytes][client] += 1
        for bytes in dls:
            x, y = getcdf(dls[bytes].values(), shownpercentile=1.0)
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in figs:
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Downloads Completed (\#)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("number of {0} byte downloads completed, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_throughput(tgendata, page, args):

    f = None

    for (d, label, lineformat) in tgendata:
        points = []
        for node in d:
            for transfer in d[node]['firstbyte']:
                if f is None: f = pylab.figure()
                size = float(transfer)/1048576.0
                for time in d[node]['firstbyte'][transfer]:
                    points += [(int(time), size)]

        points = sorted(points) # sorts by first value of tuple
        x = [i for i in range(points[0][0], points[-1][0] + 1)]
        y = [0] * len(x)

        for p in points:
            y[p[0] - x[0]] += p[1]

        y_ma = movingaverage(y, 300)
        x_rel = [x_i - x[0] for x_i in x]
        pylab.plot(x_rel, y_ma, lineformat, label=label)
        pylab.xlim(xmin=0)

    if f is not None:
        pylab.xlabel("Tick (s)")
        pylab.ylabel("Throughput (MiB/s)")
        if not args.notitle: pylab.title("5 minute moving average throughput tgen, all nodes")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_firstbyte(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        fb = []
        for client in d:
            if "firstbyte" in d[client]:
                for b in d[client]["firstbyte"]:
                    if f is None: f = pylab.figure()
                    for sec in d[client]["firstbyte"][b]: fb.extend(d[client]["firstbyte"][b][sec])
        if f is not None and len(fb) > 0:
            x, y = getcdf(fb)
            pylab.plot(x, y, lineformat, label=label)

    if f is not None:
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to download first byte, all clients")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_lastbyte_all(data, page, info, args):
    figs = {'combined': pylab.figure()}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            if "lastbyte" in d[client]:
                for b in d[client]["lastbyte"]:
                    bytes = int(b)
                    if bytes not in figs: figs[bytes] = pylab.figure()
                    if bytes not in lb: lb[bytes] = []
                    for sec in d[client]["lastbyte"][b]: lb[bytes].extend(d[client]["lastbyte"][b][sec])
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)
            pylab.figure(figs['combined'].number)
            pylab.plot(x, y, lineformat, label=label)

            if x and y:
                info.write("--- global transfer info - {0}, {1} bytes ---\n".format(label, bytes))
                info.write("mean time to last byte (s): {0}\n".format(numpy.mean(x)))
                info.write("median time to last byte (s): {0}\n".format(numpy.median(x)))
                info.write("total throughput (MiB): {0}\n ".format(int(bytes/1048576.0 * len(lb[bytes]))))
                info.write("\n");

    for key in sorted(figs.keys()):
        pylab.figure(figs[key].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if key == 'combined':
            if not args.notitle: pylab.title("time to download last byte, all downloads")
        else:
            if not args.notitle: pylab.title("time to download {0} bytes, all downloads".format(key))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_lastbyte_median(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            if "lastbyte" in d[client]:
                for b in d[client]["lastbyte"]:
                    bytes = int(b)
                    if bytes not in figs: figs[bytes] = pylab.figure()
                    if bytes not in lb: lb[bytes] = []
                    client_lb_list = []
                    for sec in d[client]["lastbyte"][b]: client_lb_list.extend(d[client]["lastbyte"][b][sec])
                    if len(client_lb_list) > 0: lb[bytes].append(numpy.median(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("median time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_lastbyte_mean(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            if "lastbyte" in d[client]:
                for b in d[client]["lastbyte"]:
                    bytes = int(b)
                    if bytes not in figs: figs[bytes] = pylab.figure()
                    if bytes not in lb: lb[bytes] = []
                    client_lb_list = []
                    for sec in d[client]["lastbyte"][b]: client_lb_list.extend(d[client]["lastbyte"][b][sec])
                    if len(client_lb_list) > 0: lb[bytes].append(numpy.mean(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("mean time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_lastbyte_max(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        lb = {}
        for client in d:
            if "lastbyte" in d[client]:
                for b in d[client]["lastbyte"]:
                    bytes = int(b)
                    if bytes not in figs: figs[bytes] = pylab.figure()
                    if bytes not in lb: lb[bytes] = []
                    client_lb_list = []
                    for sec in d[client]["lastbyte"][b]: client_lb_list.extend(d[client]["lastbyte"][b][sec])
                    if len(client_lb_list) > 0: lb[bytes].append(numpy.max(client_lb_list))
        for bytes in lb:
            x, y = getcdf(lb[bytes])
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Download Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("max time to download {0} bytes, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_downloads(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        dls = {}
        for client in d:
            if "lastbyte" in d[client]:
                for b in d[client]["lastbyte"]:
                    bytes = int(b)
                    if bytes not in figs: figs[bytes] = pylab.figure()
                    if bytes not in dls: dls[bytes] = {}
                    if client not in dls[bytes]: dls[bytes][client] = 0
                    for sec in d[client]["lastbyte"][b]: dls[bytes][client] += len(d[client]["lastbyte"][b][sec])
        for bytes in dls:
            x, y = getcdf(dls[bytes].values(), shownpercentile=1.0)
            pylab.figure(figs[bytes].number)
            pylab.plot(x, y, lineformat, label=label)

    for bytes in sorted(figs.keys()):
        pylab.figure(figs[bytes].number)
        pylab.xlabel("Downloads Completed (\#)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("number of {0} byte downloads completed, each client".format(bytes))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_errors(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        dls = {}
        for client in d:
            if "errors" in d[client]:
                for code in d[client]["errors"]:
                    if code not in figs: figs[code] = pylab.figure()
                    if code not in dls: dls[code] = {}
                    if client not in dls[code]: dls[code][client] = 0
                    for sec in d[client]["errors"][code]: dls[code][client] += len(d[client]["errors"][code][sec])
        for code in dls:
            x, y = getcdf([dls[code][client] for client in dls[code]], shownpercentile=1.0)
            pylab.figure(figs[code].number)
            pylab.plot(x, y, lineformat, label=label)

    for code in sorted(figs.keys()):
        pylab.figure(figs[code].number)
        pylab.xlabel("Download Errors (\#)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("number of transfer {0} errors, each client".format(code))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_errsizes_all(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        err = {}
        for client in d:
            if "errors" in d[client]:
                for code in d[client]["errors"]:
                    if code not in figs: figs[code] = pylab.figure()
                    client_err_list = []
                    for sec in d[client]["errors"][code]: client_err_list.extend(d[client]["errors"][code][sec])
                    if len(client_err_list) > 0:
                        if code not in err: err[code] = []
                        for b in client_err_list: err[code].append(int(b)/1024.0)
        for code in err:
            x, y = getcdf(err[code])
            pylab.figure(figs[code].number)
            pylab.plot(x, y, lineformat, label=label)

    for code in sorted(figs.keys()):
        pylab.figure(figs[code].number)
        pylab.xlabel("Data Transferred (KiB)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("bytes transferred before {0} error, all downloads".format(code))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_errsizes_median(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        err = {}
        for client in d:
            if "errors" in d[client]:
                for code in d[client]["errors"]:
                    if code not in figs: figs[code] = pylab.figure()
                    client_err_list = []
                    for sec in d[client]["errors"][code]: client_err_list.extend(d[client]["errors"][code][sec])
                    if len(client_err_list) > 0:
                        if code not in err: err[code] = []
                        err[code].append(numpy.median(client_err_list)/1024.0)
        for code in err:
            x, y = getcdf(err[code])
            pylab.figure(figs[code].number)
            pylab.plot(x, y, lineformat, label=label)

    for code in sorted(figs.keys()):
        pylab.figure(figs[code].number)
        pylab.xlabel("Data Transferred (KiB)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("median bytes transferred before {0} error, each client".format(code))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tgen_errsizes_mean(data, page, args):
    figs = {}

    for (d, label, lineformat) in data:
        err = {}
        for client in d:
            if "errors" in d[client]:
                for code in d[client]["errors"]:
                    if code not in figs: figs[code] = pylab.figure()
                    client_err_list = []
                    for sec in d[client]["errors"][code]: client_err_list.extend(d[client]["errors"][code][sec])
                    if len(client_err_list) > 0:
                        if code not in err: err[code] = []
                        err[code].append(numpy.mean(client_err_list)/1024.0)
        for code in err:
            x, y = getcdf(err[code])
            pylab.figure(figs[code].number)
            pylab.plot(x, y, lineformat, label=label)

    for code in sorted(figs.keys()):
        pylab.figure(figs[code].number)
        pylab.xlabel("Data Transferred (KiB)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("mean bytes transferred before {0} error, each client".format(code))
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_tor(data, page, args, capacities=None, direction="bytes_written"):
    mafig = pylab.figure()
    allcdffig = pylab.figure()
    eachcdffig = pylab.figure()
    capsfig = None if capacities == None else pylab.figure()

    for (d, label, lineformat) in data:
        tput = {}
        pertput, percap = [], []
        for node in d:
            for tstr in d[node][direction]:
                mib = d[node][direction][tstr]/1048576.0
                t = int(tstr)
                if t not in tput: tput[t] = 0
                tput[t] += mib
                pertput.append(mib)
                if capacities != None:
                    nick = node.split('~')[0]
                    if nick in capacities:
                        percap.append(mib/capacities[nick]*100.0)

        pylab.figure(mafig.number)
        x = sorted(tput.keys())
        y = [tput[t] for t in x]
        y_ma = movingaverage(y, 60)
        pylab.scatter(x, y, s=0.1)
        pylab.plot(x, y_ma, lineformat, label=label)

        pylab.figure(allcdffig.number)
        x, y = getcdf(y)
        pylab.plot(x, y, lineformat, label=label)

        pylab.figure(eachcdffig.number)
        x, y = getcdf(pertput)
        pylab.plot(x, y, lineformat, label=label)

        if capacities != None and len(percap) > 0:
            pylab.figure(capsfig.number)
            x, y = getcdf(percap)
            pylab.plot(x, y, lineformat, label=label)

    pylab.figure(mafig.number)
    pylab.xlabel("Tick (s)")
    pylab.ylabel("Throughput (MiB/s)")
    pylab.xlim(xmin=0.0)
    pylab.ylim(ymin=0.0)
    if not args.notitle: pylab.title("60 second moving average throughput, {0}, all relays".format("write" if direction == "bytes_written" else "read"))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(mafig)

    pylab.figure(allcdffig.number)
    pylab.xlabel("Throughput (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second throughput, {0}, all relays".format("write" if direction == "bytes_written" else "read"))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(allcdffig)

    pylab.figure(eachcdffig.number)
    #pylab.xscale('log')
    pylab.xlabel("Throughput (MiB/s)")
    pylab.ylabel("Cumulative Fraction")
    if not args.notitle: pylab.title("1 second throughput, {0}, each relay".format("write" if direction == "bytes_written" else "read"))
    pylab.legend(loc="lower right")
    page.savefig()
    pylab.close()
    del(eachcdffig)

    if capacities != None:
        pylab.figure(capsfig.number)
        #pylab.xscale('log')
        pylab.xlabel("Bandwidth Utilization (percent)")
        pylab.ylabel("Cumulative Fraction")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()
        del(capsfig)

def plot_payment_numpayments(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["numpayments"]:
                    fb.extend(d[client][relaytype]["numpayments"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype + " (" + label + ")"
                pylab.plot(x, y, lineformat[relaytype][0], label=series)

    if f is not None:
        pylab.xlabel("Number of Payments (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("number of payments, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_lifetime(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["lifetime"]:
                    fb.extend(d[client][relaytype]["lifetime"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype
                pylab.plot(x, y, lineformat[relaytype][0], label=series)

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("total lifetime, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_ttestablish(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttestablish"]:
                    fb.extend(d[client][relaytype]["ttestablish"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype
                pylab.plot(x, y, lineformat[relaytype][0], label=series)
                pylab.xlim(xmax=15);

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to establish, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_ttpayment(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttpayment"]:
                    fb.extend(d[client][relaytype]["ttpayment"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype
                pylab.plot(x, y, lineformat[relaytype][0], label=series)
                pylab.xlim(xmax=15);

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to complete payment, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_ttpaysuccess(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttpaysuccess"]:
                    fb.extend(d[client][relaytype]["ttpaysuccess"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype
                pylab.plot(x, y, lineformat[relaytype][0], label=series)
                pylab.xlim(xmax=15);

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to first payment, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_ttclose(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttclose"]:
                    fb.extend(d[client][relaytype]["ttclose"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype
                pylab.plot(x, y, lineformat[relaytype][0], label=series)
                pylab.xlim(xmax=15);

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("time to close, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_payment_efficiency(data, page, args):
    f = None

    for (d, label, lineformat) in data:
        for relaytype in ["guard", "middle", "exit"]:
            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttpayment"]:
                    fb.extend(d[client][relaytype]["ttpayment"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype + " send"
                pylab.plot(x, y, lineformat[relaytype][0], label=series)
                pylab.xlim(xmax=15);

            fb = []
            for client in d:
                if f is None: f = pylab.figure()
                for sec in d[client][relaytype]["ttpaysuccess"]:
                    fb.extend(d[client][relaytype]["ttpaysuccess"][sec])
            if f is not None and len(fb) > 0:
                x, y = getcdf(fb)
                series = relaytype + " call"
                pylab.plot(x, y, lineformat[relaytype][1], label=series)
                pylab.xlim(xmax=15);

    if f is not None:
        pylab.xlabel("Elapsed Time (s)")
        pylab.ylabel("Cumulative Fraction")
        if not args.notitle: pylab.title("payment efficiency, all nanochannels")
        pylab.legend(loc="lower right")
        page.savefig()
        pylab.close()

def plot_payment_traffic(data, info, args):
    traffic = {}

    for (d, label, lineformat) in data:
        for client in d:
            for ntype in d[client]['traffic']:
                if ntype not in traffic:
                    traffic[ntype] = 0
                traffic[ntype] += d[client]['traffic'][ntype]

    info.write("--- total payment traffic - all ---\n")
    for ntype in traffic:
        info.write("{0}: {1} messages\n".format(ntype, traffic[ntype]))
    info.write("\n");

def get_data(experiments, lineformats, skiptime, rskiptime, hostpatternshadow, hostpatterntgen, hostpatterntor, hostpatternpayment):
    tickdata, shdata, ftdata, tgendata, tordata, paymentdata = [], [], [], [], [], []
    lflist = lineformats.strip().split(",")

    lfcycle = cycle(lflist)
    for (path, label) in experiments:
        log = os.path.abspath(os.path.expanduser("{0}/stats.shadow.json.xz".format(path)))
        if not os.path.exists(log): continue
        xzcatp = subprocess.Popen(["xzcat", log], stdout=subprocess.PIPE)
        data = json.load(xzcatp.stdout)
        data = prune_data(data, skiptime, rskiptime, hostpatternshadow)

        nextcycle = lfcycle.next()
        if 'nodes' in data and len(data['nodes']) > 0:
            shdata.append((data['nodes'], label, nextcycle))
        if 'ticks' in data and len(data['ticks']) > 0:
            tickdata.append((data['ticks'], label, nextcycle))

    lfcycle = cycle(lflist)
    for (path, label) in experiments:
        log = os.path.abspath(os.path.expanduser("{0}/stats.filetransfer.json.xz".format(path)))
        if not os.path.exists(log): continue
        xzcatp = subprocess.Popen(["xzcat", log], stdout=subprocess.PIPE)
        data = json.load(xzcatp.stdout)
        data = prune_data(data, skiptime, rskiptime, hostpatterntgen)
        if 'nodes' in data and len(data['nodes']) > 0:
            ftdata.append((data['nodes'], label, lfcycle.next()))

    lfcycle = cycle(lflist)
    for (path, label) in experiments:
        log = os.path.abspath(os.path.expanduser("{0}/stats.tgen.json.xz".format(path)))
        if not os.path.exists(log): continue
        xzcatp = subprocess.Popen(["xzcat", log], stdout=subprocess.PIPE)
        data = json.load(xzcatp.stdout)
        data = prune_data(data, skiptime, rskiptime, hostpatterntgen)
        if 'nodes' in data and len(data['nodes']) > 0:
            tgendata.append((data['nodes'], label, lfcycle.next()))

    lfcycle = cycle(lflist)
    for (path, label) in experiments:
        log = os.path.abspath(os.path.expanduser("{0}/stats.tor.json.xz".format(path)))
        if not os.path.exists(log): continue
        xzcatp = subprocess.Popen(["xzcat", log], stdout=subprocess.PIPE)
        data = json.load(xzcatp.stdout)
        data = prune_data(data, skiptime, rskiptime, hostpatterntor)
        if len(data['nodes']) > 0: tordata.append((data['nodes'], label, lfcycle.next()))

    lfcycle = cycle(lflist)
    for (path, label) in experiments:
        log = os.path.abspath(os.path.expanduser("{0}/stats.payment.json.xz".format(path)))
        if not os.path.exists(log): continue
        xzcatp = subprocess.Popen(["xzcat", log], stdout=subprocess.PIPE)
        data = json.load(xzcatp.stdout)
        data = prune_data(data, skiptime, rskiptime, hostpatternpayment)
        if 'nodes' in data and len(data['nodes']) > 0:
            lineformats = {}
            lineformats["guard"] = [lfcycle.next(), lfcycle.next()]
            lineformats["middle"] = [lfcycle.next(), lfcycle.next()]
            lineformats["exit"] = [lfcycle.next(), lfcycle.next()]
            paymentdata.append((data['nodes'], label, lineformats))

    return tickdata, shdata, ftdata, tgendata, tordata, paymentdata

def prune_data(data, skiptime, rskiptime, hostpattern):
    if 'nodes' in data:
        # avoid modifying the dict while iterating it
        names_to_remove = []
        for name in data['nodes']:
            found = True if search(hostpattern, name) else False
            if not found: names_to_remove.append(name)
        for name in names_to_remove:
            del(data['nodes'][name])

    if skiptime == 0 and rskiptime == 0: return data

    if 'nodes' in data:
        for name in data['nodes']:
            keys = ['recv', 'send', 'errors', 'firstbyte', 'lastbyte']
            for k in keys:
                if k in data['nodes'][name]:
                    for header in data['nodes'][name][k]:
                        unwanted = set()
                        for sec in data['nodes'][name][k][header]:
                            if (skiptime > 0 and int(sec) < skiptime) or (rskiptime > 0 and int(sec) > rskiptime):
                                unwanted.add(sec)
                        for sec in unwanted:
                            del(data['nodes'][name][k][header][sec])
            keys = ['bytes_read', 'bytes_written']
            for k in keys:
                if k in data['nodes'][name]:
                    unwanted = set()
                    for sec in data['nodes'][name][k]:
                        if (skiptime > 0 and int(sec) < skiptime) or (rskiptime > 0 and int(sec) > rskiptime):
                            unwanted.add(sec)
                    for sec in unwanted:
                        del(data['nodes'][name][k][sec])
    return data

def get_relay_capacities(shadow_config_path, bwup=False, bwdown=False):
    if not bwup and not bwdown:
        return None
    from lxml import etree
    # shadow_config_path should be a specific file
    # this will go through all the relays listed
    # and extract the "true" bandwidth for each
    # return a dict of nickname->true_bandwidth
    relays = {}
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(shadow_config_path, parser)
    root = tree.getroot()
    for n in root.iterchildren("node"):
        nick = n.get('id')
        if 'relay' not in nick and 'thority' not in nick:
            continue
        l = []
        if bwup:
            if n.get('bandwidthup') != None:
                l.append(int(n.get('bandwidthup'))/1024.0) # KiB/s to MiB/s
            else:
                continue
        if bwdown:
            if n.get('bandwidthdown') != None:
                l.append(int(n.get('bandwidthdown'))/1024.0) # KiB/s to MiB/s
            else:
                continue
        relays[nick] = min(l)
    return relays

# helper - compute the window_size moving average over the data in interval
def movingaverage(interval, window_size):
    if len(interval) > 0:
        window = numpy.ones(int(window_size))/float(window_size)
        return numpy.convolve(interval, window, 'same')
    else:
        return []

## helper - cumulative fraction for y axis
def cf(d): return pylab.arange(1.0,float(len(d))+1.0)/float(len(d))

## helper - return step-based CDF x and y values
## only show to the 99th percentile by default
def getcdf(data, shownpercentile=0.99, maxpoints=100000.0):
    data.sort()
    frac = cf(data)
    k = len(data)/maxpoints
    x, y, lasty = [], [], 0.0
    for i in xrange(int(round(len(data)*shownpercentile))):
        if i % k > 1.0: continue
        assert not numpy.isnan(data[i])
        x.append(data[i])
        y.append(lasty)
        x.append(data[i])
        y.append(frac[i])
        lasty = frac[i]
    return x, y

def type_nonnegative_integer(value):
    i = int(value)
    if i < 0: raise argparse.ArgumentTypeError("%s is an invalid non-negative int value" % value)
    return i

def type_str_path_in(value):
    s = str(value)
    p = os.path.abspath(os.path.expanduser(s))
    if not os.path.exists(p):
        raise argparse.ArgumentTypeError("path '%s' does not exist" % s)
    return p

if __name__ == '__main__': sys.exit(main())
