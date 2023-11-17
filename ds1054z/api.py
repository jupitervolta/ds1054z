from jvframework.logger import log

import time
import os
import io
import pkg_resources
import csv
import sys
from itertools import zip_longest

from ds1054z import DS1054Z
from PIL import Image, ImageOps, ImageEnhance, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True


def initial_setup(ds):
    try:
        # Acquire
        ds.write(":ACQuire:TYPE NORMal")
        ds.write(":ACQuire:MDEPth AUTO")

        # Horizontal Scale
        ds.write(":TIMebase:MODE MAIN")
        ds.write(":TIMebase:DELay:ENABle OFF")
        ds.timebase_offset = 200e-6
        ds.timebase_scale = 50e-6  # Seconds

        # Channel 1
        ds.write(":CHANnel1:COUPling DC")
        ds.write(":CHANnel1:BWLimit OFF")
        ds.write(":CHANnel1:INVert OFF")
        ds.write(":CHANnel1:UNITs VOLTage")
        ds.set_probe_ratio("CHAN1", 1000)  # Multiplier (1x, 10x, 100x...)

        voltage_scale = 500  # Volts/division
        voltage_offset = -2 * voltage_scale  # Divisions * volts/division
        ds.set_channel_scale("CHAN1", voltage_scale)  # Volts/division
        ds.set_channel_offset("CHAN1", voltage_offset)  # Volts

        # Channel 2
        ds.write(":CHANnel2:COUPling DC")
        ds.write(":CHANnel2:BWLimit OFF")
        ds.write(":CHANnel2:INVert OFF")
        ds.write(":CHANnel2:UNITs AMPere")
        ds.set_probe_ratio("CHAN2", 10)  # Multiplier (1x, 10x, 100x...)

        current_scale = 1  # kA/division
        current_offset = -2 * current_scale  # Divisions * kA/division
        ds.set_channel_scale("CHAN2", current_scale)  # kA/division
        ds.set_channel_offset("CHAN2", current_offset)  # kA

        # Trigger
        ds.write(":TRIGger:MODE EDGE")
        ds.write(":TRIGger:EDGe:SOURce CHANnel2")
        ds.write(":TRIGger:EDGe:SLOPe POSitive")  # {POSitive|NEGative|RFALl}
        ds.write(":TRIGger:NREJect ON")
        ds.write(":TRIGger:COUPling DC")
        ds.write(":TRIGger:EDGe:LEVel 0.5")
        return True
    except Exception as e:
        log(e)
        return {"error": str(e)}


def screenshot_simple(ds, filepath):
    try:
        im = Image.open(io.BytesIO(ds.display_data))
        im = im.convert("RGB")
        im.save(filepath, format="png")
        return filepath
    except Exception as e:
        log(e)
        return {"error": str(e)}


def screenshot_fancy(
    ds,
    filepath,
    *args,
    sample_time=None,
    overlay_alpha=1,
    printable=False,
    verbose=False,
    **kwargs,
):
    try:
        # fmt = None
        # if filename:
        #     fmt = filename
        # else:
        #     fmt = "scope-display_{ts}.png"
        # ts = (
        #     sample_time
        #     if sample_time
        #     else time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        # )
        # filename = fmt.format(ts=ts)
        # need to find out file extension for Pillow on Windows...
        ext = os.path.splitext(filepath)[1]
        if not ext:
            log("Could not detect the image file type extension from the filename")
            return False
        # getting and saving the image
        im = Image.open(io.BytesIO(ds.display_data))
        overlay_filename = pkg_resources.resource_filename(
            "ds1054z", "resources/overlay.png"
        )
        overlay = Image.open(overlay_filename)
        alpha_100_percent = Image.new(overlay.mode, overlay.size, color=(0, 0, 0, 0))
        overlay = Image.blend(alpha_100_percent, overlay, overlay_alpha)
        im.putalpha(255)
        im = Image.alpha_composite(im, overlay)
        if printable:
            im = Image.merge("RGB", im.split()[0:3])
            im = ImageOps.invert(im)
            im = ImageEnhance.Color(im).enhance(0)
            im = ImageEnhance.Brightness(im).enhance(0.95)
            im = ImageEnhance.Contrast(im).enhance(2)
            im = im.convert("L")
            im = im.point(lambda x: x if x < 252 else 255)
        else:
            im = im.convert("RGB")
        im.save(filepath, format=ext[1:])
        if not verbose:
            log(filepath)
        else:
            log("Saved file: " + filepath)
        return True
    except Exception as e:
        log(e)
        return {"error": str(e)}


def save_waveform_simple(ds, work_dir, filename, channels):
    try:
        wave_file = os.path.join(*[work_dir, filename])
        log(f"Writing {len(channels)} waveforms to {work_dir}/{filename}")
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
    except Exception as e:
        log(e)
        return {"error": str(e)}


def save_data(
    ds,
    work_dir,
    filename,
    *args,
    sample_time=None,
    with_time=True,
    mode="NORMal",
    verbose=False,
    **kwargs,
):
    try:
        ext = os.path.splitext(filename)[-1]
        if not ext:
            log("Could not detect the file type extension from the filename")
            return False
        filepath = os.path.join(work_dir, filename)
        kind = ext[1:]
        if kind in ("csv", "txt"):
            data = []
            channels = ds.displayed_channels
            for channel in channels:
                data.append(ds.get_waveform_samples(channel, mode=mode))
            if with_time:
                data.insert(0, ds.waveform_time_values_decimal)
            lengths = [len(samples) for samples in data]
            if len(set(lengths)) != 1:
                log("Different number of samples read for different channels!")
                sys.exit(1)

            def csv_open(filepath):
                if sys.version_info >= (3, 0):
                    return open(filepath, "w", newline="")
                else:
                    return open(filepath, "wb")

            with csv_open(filepath) as csv_file:
                delimiter = "," if kind == "csv" else "\t"
                csv_writer = csv.writer(csv_file, delimiter=delimiter)
                if with_time:
                    csv_writer.writerow(["TIME"] + channels)
                else:
                    csv_writer.writerow(channels)
                for vals in zip_longest(*data):
                    if with_time:
                        vals = [vals[0]] + ["{:.2e}".format(val) for val in vals[1:]]
                    else:
                        vals = ["{:.2e}".format(val) for val in vals]
                    csv_writer.writerow(vals)
        else:
            log("This tool cannot handle the requested --type")
        if not verbose:
            log(filepath)
        else:
            log("Saved file: " + filepath)
        return True
    except Exception as e:
        log(e)
        return {"error": str(e)}


def single_mode(ds):
    try:
        ds.single()
        sent_time = time.time()
        # Wait for scope to change from previous status/mode to single mode
        # If too much time has passed, it could mean the scope triggered immediately after switching to single
        # and we missed the WAIT status.
        while ds.query(":TRIGger:STATus?") != "WAIT" and time.time() - sent_time < 1:
            pass
    except Exception as e:
        log(e)
        return {"error": str(e)}


def test_main(scope, max_itr=10):
    try:
        initial_setup(scope)
        time.sleep(2)
        log("Scope Initialized")

        single_mode(scope)
        log("Scope Ready For Trigger")

        RAW_MODE = False
        mode = "RAW" if RAW_MODE else "NORMal"

        itr = 0
        while itr < max_itr:
            scope_status = scope.query(":TRIGger:STATus?")
            if scope_status in ("TD", "AUTO", "STOP"):
                #

                timer_start = time.time()

                sample_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                log(f"Triggered. Trigger Status: {scope_status}")

                save_data(scope, sample_time=sample_time, mode=mode)
                screenshot_fancy(scope, sample_time=sample_time)
                single_mode(scope)

                log(f"Time to save data and reset: {time.time()-timer_start}")
                itr += 1
    except Exception as e:
        log(e)
        return {"error": str(e)}


def has_scope_triggered(ds):
    try:
        scope_status = ds.query(":TRIGger:STATus?")
        return scope_status in ("TD", "AUTO", "STOP")
    except Exception as e:
        log(e)
        return {"error": str(e)}


if __name__ == "__main__":
    ds = DS1054Z("10.0.1.106")
    test_main(ds)
