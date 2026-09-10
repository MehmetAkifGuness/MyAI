from boru.release import build_release


def build_application():
    return build_release('V12.0')


if __name__ == '__main__':
    build_application().mainloop()
