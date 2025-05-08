#!/usr/bin/env python3

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import OVSKernelSwitch, DefaultController
from mininet.log import setLogLevel
from time import sleep
import sys

class RTPTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        h1 = self.addHost('h1')  # vídeo origem
        h2 = self.addHost('h2')  # vídeo destino
        h3 = self.addHost('h3')  # iperf origem
        h4 = self.addHost('h4')  # iperf destino

        self.addLink(h1, s1, cls=TCLink, bw=10)
        self.addLink(h3, s1, cls=TCLink, bw=10)
        self.addLink(h2, s2, cls=TCLink, bw=10)
        self.addLink(h4, s2, cls=TCLink, bw=10)
        self.addLink(s1, s2, cls=TCLink, bw=10)

def run():
    topo = RTPTopo()
    net = Mininet(topo=topo, link=TCLink, switch=OVSKernelSwitch, controller=DefaultController)
    net.start()

    h1, h2, h3, h4 = net.get('h1', 'h2', 'h3', 'h4')
    s1, s2 = net.get('s1', 's2')

    print("Aplicando QoS na interface s1-eth3...")

    s1.cmd('tc qdisc del dev s1-eth3 root')
    s1.cmd('tc qdisc add dev s1-eth3 root handle 1: htb default 20')
    s1.cmd('tc class add dev s1-eth3 parent 1: classid 1:1 htb rate 1mbit ceil 10mbit')
    s1.cmd('tc qdisc add dev s1-eth3 parent 1:1 handle 10: prio')
    s1.cmd('tc qdisc add dev s1-eth3 parent 1:1 handle 20: tbf rate 1mbit burst 32k latency 400ms')
    s1.cmd('tc filter add dev s1-eth3 protocol ip parent 1:0 prio 1 u32 match ip dport 5004 0xffff flowid 1:1')
    s1.cmd('tc filter add dev s1-eth3 protocol ip parent 1:0 prio 1 u32 match ip dport 5006 0xffff flowid 1:1')

    print("Iniciando transmissão RTP de h1 para h2...")

    h1.cmd(
        'ffmpeg -re -i video.mp4 '
        '-map 0:v:0 -c:v libx264 -preset ultrafast -tune zerolatency '
        '-x264-params "keyint=25:scenecut=0:repeat-headers=1" '
        '-f rtp rtp://10.0.0.2:5004?pkt_size=1200 '
        '-map 0:a:0 -c:a aac -ar 44100 -b:a 128k '
        '-f rtp rtp://10.0.0.2:5006?pkt_size=1200 '
        '-sdp_file video.sdp > /tmp/ffmpeg.log 2>&1 &'
    )

    sleep(2)

    print("Iniciando ffplay em h2...")

    h2.cmd('ffplay -report -protocol_whitelist "file,udp,rtp" -fflags nobuffer -flags low_delay -i video.sdp '
       '> /tmp/ffplay.log 2>&1 &')

    sleep(2)

    print("Iniciando monitoramento da interface do link s1 <-> s2...")
    monitor = s1.popen('ifstat -i s1-eth3 0.5', stdout=sys.stdout)

    sleep(10)

    num_streams = 3
    duration = 20
    print(f"Iniciando {num_streams} fluxo(s) iperf UDP de h3 para h4 por {duration} segundos...")
    for i in range(num_streams):
        h3.cmd(f'iperf -c 10.0.0.4 -u -b 3M -t {duration} > /tmp/iperf_{i}.log 2>&1 &')

    print("Executando experimento por mais 40 segundos...")
    sleep(40)

    print("Encerrando monitoramento...")
    monitor.terminate()

    print("Encerrando rede...")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
