import sys
from conn import SerialFlasher

def usage():
    print(f"""
Usage:

Program firmware:
    {sys.argv[0]} program PORT FILE BASE

Read config region:
    {sys.argv[0]} readcfg PORT OFFSET SIZE

Erase config region:
    {sys.argv[0]} erasecfg PORT OFFSET SIZE

Write config region:
    {sys.argv[0]} writecfg PORT OFFSET FILE
""")
    sys.exit(1)


def run():
    if len(sys.argv) < 3:
        usage()

    command = sys.argv[1]
    port = sys.argv[2]

    conn = SerialFlasher(port, progress_bar=True)

    #
    # Query Device Info
    #
    if command == "info":
        conn.info()
        return

    #
    # PROGRAM
    #
    if command == "program":

        if len(sys.argv) < 4:
            usage()

        fname = sys.argv[3]

        conn.program(fname, True)
        return

    #
    # READ CONFIG
    #
    elif command == "readcfg":

        if len(sys.argv) < 5:
            usage()


        offset = int(sys.argv[3])
        total_length = int(sys.argv[4])
        
        conn.read_config(offset, total_length, True)

        return

    #
    # ERASE CONFIG
    #
    elif command == "erasecfg":

        if len(sys.argv) < 5:
            usage()

        offset = int(sys.argv[3])
        length = int(sys.argv[4])
        
        conn.erase_config(offset, length)
        print("Config region erased")
        return
    
    #
    # WRITE CONFIG
    #
    elif command == "writecfg":

        if len(sys.argv) < 5:
            usage()

        offset = int(sys.argv[3])
        fname = sys.argv[4]

        conn.write_config(offset, fname)
        return 

    else:
        usage()


def main():
    try:
        run()

    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()