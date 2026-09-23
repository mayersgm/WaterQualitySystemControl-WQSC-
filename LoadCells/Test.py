from hx711 import HX711
h = HX711()
while True:
    print(h.read_raw())
    import utime; utime.sleep_ms(500)