from jvframework.logger import log
import asyncio
import ds1054z
import os
import sys
import ds1054z.api as dapi
from jvframework.supervisor import start_supervisor
from jvframework.misc import hdd_share, ssd_share, ensure_dir
from PIL import ImageFile

ds = ds1054z.DS1054Z("10.0.1.106")
ImageFile.LOAD_TRUNCATED_IMAGES = True


async def do_work(api, *args, logger=None, **kwargs):
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
        if api in ["save_waveform", "save_waveform_simple"]:
            """
            Save waveform to file pulse_waveform_{channel}.csv
            args[0]: work_dir
            args[1:]: CHAN1 CHAN2 CHAN3 CHAN4
            """
            assert (
                len(args) >= 2
            ), "Require channel and path arguments for saving waveform"
            work_dir = hdd_share(args[0])
            ensure_dir(work_dir)
            channels = args[1:]
            return dapi.save_waveform_simple(ds, work_dir, channels)
        if api == "trigger_single":
            ds.single()
        if api in ["save_note", "save_notes"]:
            """
            Save a note to a file, simple text file
            args[0]: work_dir
            args[1]: note
            """
            assert len(args) >= 2, "Require text and path arguments for saving note"
            work_dir = hdd_share(args[0])
            ensure_dir(work_dir)
            note = args[1]
            note_file = os.path.join(*[work_dir, "note.txt"])
            log(f"Writing note of length {len(note)} to {work_dir}")
            with open(
                note_file,
                mode="w",
            ) as f:
                log("Opened file for writing:", note_file)
                f.write(note)
            return True
        if api in ["screenshot_simple", "screenshot"]:
            """
            Save screenshot to file pulse_waveform_screenshot.png
            args[0]: work_dir
            """
            # formatting the filename
            work_dir = hdd_share(args[0])
            ensure_dir(work_dir)
            filename = "pulse_waveform_screenshot.png"
            filepath = os.path.join(work_dir, filename)
            return dapi.screenshot_simple(ds, filepath)
        if api in ["screenshot_fancy"]:
            work_dir = hdd_share(args[0])
            ensure_dir(work_dir)
            return dapi.screenshot_fancy(ds, *args, work_dir=work_dir, **kwargs)
        if api == "initial_setup":
            return dapi.initial_setup(ds)
        if api == "save_data":
            work_dir = hdd_share(args[0])
            ensure_dir(work_dir)
            return dapi.save_data(ds, *args, work_dir=work_dir, **kwargs)
        if api == "single_mode":
            return dapi.single_mode(ds)
        if api == "test":
            return dapi.test_main(ds, max_itr=kwargs.get("max_itr", 10))
        if api == "has_scope_triggered":
            return dapi.has_scope_triggered(ds)
    except AssertionError as e:
        log("AssertionError (do_work)", e)
        return {"error (server)": str(e)}
    except Exception as e:
        log("Exception (do_work)", e)
        return {"error (server)": str(e)}


async def main():
    spvrc = start_supervisor(
        service_topic="jvber/tb0/oscope",
        client_id="spvr_tb0_oscope",
        verbosity_stream="DEBUG",
        verbosity_log="DEBUG",
    )

    while True:
        try:
            if not spvrc["from"].empty():
                recv_packet = spvrc["from"].get()
                log(
                    "Main thread recieved packet from Supervisor: ",
                    recv_packet,
                    logger=spvrc["logger"],
                )

                if "api" in recv_packet:
                    if "args" not in recv_packet:
                        log("No args found", logger=spvrc["logger"])
                        recv_packet["args"] = []
                    if "kwargs" not in recv_packet:
                        log("No kwargs found", logger=spvrc["logger"])
                        recv_packet["kwargs"] = {}

                    result = await do_work(
                        recv_packet["api"],
                        *recv_packet["args"],
                        logger=spvrc["logger"],
                        **recv_packet["kwargs"],
                    )
                    resp_packet = dict(recv_packet)
                    resp_packet.update({"result": result})

                spvrc["to"].put(resp_packet)
                log(
                    "Main thread sending packet to Supervisor: ",
                    resp_packet,
                    logger=spvrc["logger"],
                )

        except Exception as e:
            log("Exception (main)", e)


if __name__ == "__main__":
    asyncio.run(main())
