(tflite_env_39) prateeksha@raspberrypi:~/Desktop/wearable-navigation/wearable-navigation $ python3.9 src/vision/benchmark_w_graph.py     --video traffic_signal.mp4     --frames 300     --save-video     --dump results_pi.txt
Loading surroundings
Loading traffic
Loading walksign

Cold start load time: 0.004 sec

Running benchmark...

==== RESULTS ====
Frames processed: 300
FPS: 13.53
Avg latency: 66.58 ms
P95 latency: 77.51 ms

Per model avg latencies:
surroundings: 19.63 ms
traffic: 19.41 ms
walksign: 19.45 ms

System CPU load: 26.2%
Temperatures: {'cpu_thermal': [shwtemp(label='', current=83.7, high=None, critical=None)], 'rp1_adc': [shwtemp(label='', current=61.863, high=None, critical=None)]}
Saved per_model_latency.png
Saved latency_timeline.png
Saved temperature_timeline.png
Results saved to results_pi.txt
Video saved to benchmark_output.mp4