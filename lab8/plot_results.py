"""Standalone figure from recorded per-second measurements (requires matplotlib)."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
fig,axes=plt.subplots(3,1,figsize=(7.3,5.2),sharex=True,layout='constrained')
series=[('host_cpu_busy_pct','CPU хоста, %'),('qemu_cpu_one_core_pct','CPU QEMU, % ядра'),('qemu_rss_mib','RSS QEMU, MiB')]
for name,color,label in [('baseline','#245c9c','TCG по умолчанию'),('tb64','#bd6223','TCG кэш 64 MiB')]:
    values=[]
    for phase,offset in [('idle',0),('load',60)]:
        rows=list(csv.DictReader((ROOT/'results'/name/phase/'samples.csv').open()))
        values.extend([{**row,'x':float(row['elapsed_s'])+offset} for row in rows])
    for ax,(key,ylabel) in zip(axes,series):
        ax.plot([row['x'] for row in values],[float(row[key]) for row in values],lw=1.2,color=color,label=label)
        ax.set_ylabel(ylabel,fontsize=9);ax.grid(alpha=.2);ax.tick_params(labelsize=8)
for ax in axes:
    ax.axvline(60,color='#555555',ls='--',lw=.8);ax.set_xlim(0,120)
axes[0].legend(loc='upper right',fontsize=8,frameon=False)
axes[0].set_title('Простой 0–60 с     |     Нагрузка 60–120 с',fontsize=11,pad=12)
axes[-1].set_xlabel('Время внутри двух измерительных фаз, с',fontsize=9)
fig.savefig(ROOT/'results/profile.png',dpi=220)
print(ROOT/'results/profile.png')
