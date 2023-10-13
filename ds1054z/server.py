from jvframework.logger import log
import asyncio
import json
import ds1054z
import time
import os
import io
import csv
from jvframework.supervisor import Supervisor, start_supervisor, to_mqtt, from_mqtt
from PIL import Image, ImageOps, ImageEnhance, ImageFile

ds = ds1054z.DS1054Z("10.0.1.106")
ImageFile.LOAD_TRUNCATED_IMAGES = True


def normpath(path):
    sep = os.path.sep
    path = path.replace("/", sep).replace("\\", sep)
    parts = []
    for part in path.split(sep):
        if part == "..":
            if parts:
                parts.pop()
        elif part and part != ".":
            parts.append(part)
    new_path = sep.join(parts)
    if path.startswith(sep):
        new_path = sep + new_path
    return new_path


def hdd_share(path):
    if path.startswith("H:"):
        path = "/mnt/hdd_share" + path[2:]
    return path


def ssd_share(path):
    if path.startswith("S:"):
        path = "/mnt/ssd_share" + path[2:]
    return path


async def do_work(api, *args, **kwargs):
    try:
        log("Doing work:", api, args, kwargs)

        if api == "getattr":
            """
            Get attribute of ds1054z object
            args[0]: attribute name
            """
            assert len(args) >= 1, "Require attribute name"
            attr = args[0]
            log("getattr", (attr, getattr(ds, attr)))
            return (attr, getattr(ds, attr))
        if api == "setattr":
            """
            Set attribute of ds1054z object
            args[0]: attribute name
            args[1]: attribute value
            """
            assert len(args) >= 2, "Require attribute name and value"
            attr = args[0]
            value = args[1]
            log("setattr", (attr, value, True))
            setattr(ds, attr, value)
            return (attr, value, True)
        if api == "hasattr":
            """
            Check if ds1054z object has attribute
            args[0]: attribute name
            """
            assert len(args) >= 1, "Require attribute name"
            attr = args[0]
            log("hasattr", (attr, hasattr(ds, attr)))
            return (attr, hasattr(ds, attr))
        if api == "save_waveform":
            """
            Save waveform to file pulse_waveform_{channel}.csv
            args[0]: work_dir
            args[1:]: CHAN1 CHAN2 CHAN3 CHAN4
            """
            assert (
                len(args) >= 2
            ), "Require channel and path arguments for saving waveform"
            work_dir = hdd_share(normpath(args[0]))
            channels = args[1:]
            
            wave_file = os.path.join(*[work_dir, f"pulse_waveforms.csv"])
            log(f"Writing {len(channels)} waveforms to {work_dir}")
            if not os.path.exists(work_dir):
                log("Path {} does not exist, creating".format(work_dir))
                os.makedirs(work_dir)
            with open(
                wave_file,
                mode="w",
                newline="",
            ) as f:
                csv_writer = csv.writer(f)
                log("Opened file for writing:", wave_file)
                csv_writer.writerow(ds.waveform_time_values_decimal)
                for channel in channels:
                    waveform = ds.get_waveform_samples(channel)
                    csv_writer.writerow(waveform)
            return True
        if api == "trigger_single":
            ds.single()
        if api in ["save_note", "save_notes"]:
            """
            Save a note to a file, simple text file
            args[0]: work_dir
            args[1]: note
            """
            assert len(args) >= 2, "Require text and path arguments for saving note"
            work_dir = hdd_share(normpath(args[0]))
            note = args[1]
            note_file = os.path.join(*[work_dir, "note.txt"])
            log(f"Writing note of length {len(note)} to {work_dir}")
            if not os.path.exists(work_dir):
                log("Path {} does not exist, creating".format(work_dir))
                os.makedirs(work_dir)
            with open(
                note_file,
                mode="w",
            ) as f:
                log("Opened file for writing:", note_file)
                f.write(note)
            return True
        if api in ["save_screenshot", "save_screen", "screenshot"]:
            """
            Save screenshot to file pulse_waveform_screenshot.png
            args[0]: work_dir
            """
            # formatting the filename
            work_dir = hdd_share(normpath(args[0]))
            filename = "pulse_waveform_screenshot.png"
            filepath = os.path.join(work_dir, filename)

            im = Image.open(io.BytesIO(ds.display_data))
            im = im.convert("RGB")
            im.save(filepath, format="png")

    except AssertionError as e:
        log("AssertionError (do_work)", e)
        return e
    except Exception as e:
        log("Exception (do_work)", e)
        return e


async def main():
    spvrc = start_supervisor(topic="jvber/tb0/oscope/cmd", client_id="spvr_tb0_oscope")

    while True:
        try:
            if not spvrc["from"].empty():
                recv_packet = spvrc["from"].get()
                log("Main thread recieved packet from Supervisor: ", recv_packet)

                if "api" in recv_packet:
                    if "args" not in recv_packet:
                        log("No args found")
                        recv_packet["args"] = []
                    if "kwargs" not in recv_packet:
                        log("No kwargs found")
                        recv_packet["kwargs"] = {}

                    result = await do_work(
                        recv_packet["api"],
                        *recv_packet["args"],
                        **recv_packet["kwargs"],
                    )
                    resp_packet = dict(recv_packet)
                    resp_packet.update({"result": result})

                spvrc["to"].put(resp_packet)
                log("Main thread sending packet to Supervisor: ", resp_packet)

        except Exception as e:
            log("Exception (main)", e)

if __name__ == "__main__":
    asyncio.run(main())
