#!/usr/bin/python
"""executes comskip and then removes the commercials from the file"""
import subprocess
import os
import re
import sys
from time import gmtime, strftime


class ComDeleteParameters(object):
    """holds all the reused file names and details"""
    # pylint: disable=too-many-instance-attributes
    # Eight is reasonable in this case.

    # pylint: disable=too-few-public-methods
    # don't want to create
    def __init__(self, input_file):
        """creates an instance of the parameter object"""
        self.input_file = os.path.realpath(input_file)
        self.directory = os.path.dirname(self.input_file)
        _, self.file_extension = os.path.splitext(self.input_file)
        self.base_file_name = os.path.basename(
            input_file).replace(self.file_extension, '')
        self.archive_file = os.path.join(self.directory, '.' +
                                         os.path.basename(self.input_file))
        self.output_file_extension = '.mp4'
        self.output_file = self.input_file.replace(
            self.file_extension, self.output_file_extension)
        self.cut_file = self.input_file.replace(
            self.file_extension, '.txt')
        self.temporary_merge_file = self.input_file.replace(
            self.file_extension, '.skip.mp4')
        self.temporary_convert_file = self.input_file.replace(
            self.file_extension, 'x264.mp4')
        self.log_file = self.input_file.replace(
            self.file_extension, '.log')
        self.cut_lines = []
        self.shows = []
        self.commercials = []
        self.intermediate_files = dict()


def run_comskip(params):
    """executes conskip on the input file"""
    os.chdir(params.directory)
    cmd = '/usr/local/bin/comskip "%s" "%s"' % (
        params.input_file, params.directory)
    print cmd
    with open(params.log_file, 'w+') as logfile:
        logfile.writelines(strftime("%Y-%m-%d %H:%M:%S", gmtime()))
        proc = subprocess.Popen(cmd, shell=True, stdout=logfile,
                                stderr=logfile,
                                universal_newlines=True)
        proc.wait()
    print proc.returncode


def read_cut_file(params):
    """reads the cut file created by comskip"""
    os.chdir(params.directory)
    with open(params.cut_file, 'r') as cut_file:
        for i, line in enumerate(cut_file):
            if i < 2:
                continue
            params.cut_lines.append(line)


def get_frame_rate(file_name):
    """uses ffprobe to get framerate"""
    directory = os.path.dirname(os.path.realpath(file_name))
    os.chdir(directory)
    cmd = '/usr/local/bin/ffprobe -v 0 -of compact=p=0 -select_streams 0 '
    cmd = '%s -show_entries stream=r_frame_rate "%s"' % (
        cmd, file_name)
    print cmd
    out = subprocess.check_output(cmd, shell=True)
    rate = out.split('=')[1].rstrip().split('/')
    if len(rate) == 1:
        return float(rate[0])
    if len(rate) == 2:
        return float(rate[0]) / float(rate[1])
    return -1


def get_cut_time_stamp(index, params):
    """returns the timestamp from one line of the comskip output"""
    if index >= len(params.cut_lines):
        return None
    line = params.cut_lines[index]
    matches = re.findall('[0-9]+', line)
    result = ((float(matches[0]) / params.frame_rate) + 5,
              (float(matches[1]) / params.frame_rate))
    return result


def get_cuts(params):
    """combines the timestamps from consecutive lines into start and end of show segments"""
    params.frame_rate = get_frame_rate(params.input_file)
    # first iteration is a little odd because the file has commercials called out
    current_time_stamp = get_cut_time_stamp(0, params)
    if current_time_stamp[0] > float(1) / params.frame_rate:
        params.shows.append((1, current_time_stamp[0]))
    for inx, _ in enumerate(params.cut_lines):
        current_time_stamp = get_cut_time_stamp(inx, params)
        next_time_stamp = get_cut_time_stamp(inx + 1, params)
        if next_time_stamp is not None:
            params.shows.append((current_time_stamp[1], next_time_stamp[0]))
        else:
            params.shows.append((current_time_stamp[1], None))
        params.commercials.append(
            (current_time_stamp[0], current_time_stamp[1]))


def split_shows(params):
    """splits the movie to the show segments"""
    os.chdir(params.directory)
    # processes = []
    for inx, val in enumerate(params.shows):
        outfile = os.path.join(params.directory, str(
            inx) + os.path.basename(params.output_file))
        params.intermediate_files[inx] = outfile
        codec = '-c:v copy -c:a copy'

        inputstart = '-ss {start}'.format(start=val[0])

        if val[1] is None:
            duration = ''
        else:
            duration = '-t {duration}'.format(duration=(val[1] - val[0]))
        cmd = 'ffmpeg {inputstart} -i "{in_file}" -y {codec} {duration} "{outfile}"'.format(
            inputstart=inputstart, in_file=params.input_file,
            codec=codec, duration=duration, outfile=outfile)
        print cmd
        with open(params.log_file, 'w+') as logfile:
            logfile.writelines(strftime("%Y-%m-%d %H:%M:%S", gmtime()))
            proc = subprocess.Popen(cmd, shell=True,
                                    stdout=logfile,
                                    stderr=logfile,
                                    universal_newlines=True)
            proc.wait()
            print proc.returncode


def combine_shows(params):
    """combines all the parts back into one"""
    os.chdir(params.directory)
    cmd = 'ffmpeg -f concat -safe 0 -i "%s" -y -c copy "%s"' % (
        'mylist.txt', params.temporary_merge_file)
    print cmd

    with open('mylist.txt', 'w+') as listfile:
        for key in params.intermediate_files:
            listfile.writelines(
                "file '" + params.intermediate_files[key] + "'" + os.linesep)

    with open(params.log_file, 'w+') as logfile:
        logfile.writelines(strftime("%Y-%m-%d %H:%M:%S", gmtime()))
        proc = subprocess.Popen(
            cmd, shell=True, stdout=logfile,
            stderr=logfile,
            universal_newlines=True)
        proc.wait()
    # loop over the temporary video files and delete them
    for key in params.intermediate_files:
        os.remove(params.intermediate_files[key])

    # hide the source file so that we don't end up with two versions to in plex
    if os.path.isfile(params.input_file) and os.path.isfile(params.temporary_merge_file):
        os.rename(params.input_file, params.archive_file)
        os.rename(params.temporary_merge_file, params.output_file)


def cleanup(params):
    """deletes temp files"""
    # first change to the right directory
    os.chdir(params.directory)

    # delete the list of files used to recombine the files
    if os.path.isfile("./mylist.txt"):
        os.remove("./mylist.txt")
    # delete the chapter file
    # right now disabled in case I need to diagnose issues
    if os.path.isfile("./cut.chp"):
        pass
        # os.remove("./cut.chp")

    # delete the default comskip output file
    if os.path.isfile(params.cut_file):
        os.remove(params.cut_file)

    # delete the ffmpeg log this may be commented out for troubleshooting
    if os.path.isfile(params.log_file):
        pass
        os.remove(params.log_file)


def main(input_file):
    """main method run when script is executed"""
    params = ComDeleteParameters(input_file)
    if not os.path.isfile(params.input_file) and os.path.isfile(params.archive_file):
        os.rename(params.archive_file, params.input_file)
    if not os.path.isfile(params.cut_file):
        run_comskip(params)
    # (shows, _) = get_chapters(read_chapter_file(input_file))
    read_cut_file(params)
    get_cuts(params)
    split_shows(params)
    combine_shows(params)
    # convert_file(input_file)
    cleanup(params)


if __name__ == "__main__":
    main(sys.argv[1])
    sys.exit(0)
