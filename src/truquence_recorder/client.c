/* Local transport only. Never resend a request after any bytes were sent. */
#define _DARWIN_C_SOURCE
#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/time.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <time.h>
#define LIMIT (1024 * 1024)

static int fail(void) {
    const char message[] = "SignWarden Recorder could not record this event (transport).\n";
    write(2, message, sizeof(message) - 1);
    return 1;
}
static void timed_out(int sig) { (void)sig; _exit(fail()); }
static int transfer(int fd, void *data, size_t size, int sending) {
    char *p = data;
    while (size) {
        ssize_t n = sending ? write(fd, p, size) : read(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; size -= (size_t)n;
    }
    return 0;
}
static int connect_local(const char *name) {
    struct stat st;
    if (lstat(name, &st) || !S_ISSOCK(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 077)) return -1;
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr)); addr.sun_family = AF_UNIX;
    if (strlen(name) >= sizeof(addr.sun_path)) { close(fd); return -1; }
    strcpy(addr.sun_path, name);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr))) { close(fd); return -1; }
    return fd;
}
static int regular_lock(const char *path) {
    int fd = open(path, O_CREAT | O_RDWR | O_NOFOLLOW | O_NONBLOCK, 0600);
    struct stat st;
    if (fd < 0) return -1;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 077)) {
        close(fd); return -1;
    }
    return fd;
}
int main(int argc, char **argv) {
    signal(SIGPIPE, SIG_IGN);
    signal(SIGALRM, timed_out);
    struct itimerval timer = {{0, 0}, {2, 0}};
    setitimer(ITIMER_REAL, &timer, NULL);
    const char *home = getenv("HOME");
    if (argc != 3 || !home || home[0] != '/' || (argv[1][0] != '/' && strcmp(argv[1], "python3")) || argv[2][0] != '/' || strlen(home) > 8192 || strlen(argv[2]) > 8192) return fail();
    unsigned char *input = malloc(LIMIT + 1);
    if (!input) return fail();
    size_t used = 0;
    while (used <= LIMIT) {
        ssize_t n = read(0, input + used, LIMIT + 1 - used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) return fail();
        if (!n) break;
        used += (size_t)n;
        if (used > LIMIT) return fail();
    }
    uint64_t hash = UINT64_C(14695981039346656037);
    for (const unsigned char *p = (const unsigned char *)home; *p; ++p) hash = (hash ^ *p) * UINT64_C(1099511628211);
    for (const unsigned char *p = (const unsigned char *)argv[2]; *p; ++p) hash = (hash ^ *p) * UINT64_C(1099511628211);
    char directory[90], socket_name[104], lock_name[104];
#ifdef __APPLE__
    const char *temporary = "/private/tmp";
#else
    const char *temporary = "/tmp";
#endif
    snprintf(directory, sizeof(directory), "%s/swr-%lu-%016llx", temporary, (unsigned long)getuid(), (unsigned long long)hash);
    struct stat st;
    if (mkdir(directory, 0700) && errno != EEXIST) return fail();
    if (lstat(directory, &st) || !S_ISDIR(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 077)) return fail();
    snprintf(socket_name, sizeof(socket_name), "%s/socket", directory);
    snprintf(lock_name, sizeof(lock_name), "%s/start.lock", directory);
    int fd = connect_local(socket_name);
    if (fd < 0) {
        int lock = regular_lock(lock_name);
        if (lock < 0) return fail();
        int leader = !flock(lock, LOCK_EX | LOCK_NB);
        if (leader) {
            /* Another client may have completed startup before this lock. */
            fd = connect_local(socket_name);
            if (fd < 0) {
                pid_t pid = fork();
                if (pid < 0) { close(lock); return fail(); }
                if (!pid) {
                    close(lock); setsid();
                    int nullfd = open("/dev/null", O_RDWR);
                    if (nullfd < 0) _exit(1);
                    dup2(nullfd, 0); dup2(nullfd, 1); dup2(nullfd, 2);
                    if (nullfd > 2) close(nullfd);
                    execlp(argv[1], argv[1], "-S", argv[2], "--worker", directory, (char *)NULL);
                    _exit(1);
                }
            }
        }
        struct timespec pause = {0, 1000000};
        for (int i = 0; fd < 0 && i < 1200; ++i) {
            nanosleep(&pause, NULL); fd = connect_local(socket_name);
        }
        close(lock);
        if (fd < 0) return fail();
    }
    /* HOME and runner are checked by the worker: hash collisions cannot cross homes. */
    uint32_t sizes[3] = {(uint32_t)strlen(home), (uint32_t)strlen(argv[2]), (uint32_t)used};
    if (transfer(fd, sizes, sizeof(sizes), 1) || transfer(fd, (void *)home, sizes[0], 1) ||
        transfer(fd, argv[2], sizes[1], 1) || transfer(fd, input, used, 1)) return fail();
    unsigned char status;
    uint32_t length;
    if (transfer(fd, &status, 1, 0) || transfer(fd, &length, 4, 0) || length > LIMIT) return fail();
    if (transfer(fd, input, length, 0)) return fail();
    close(fd);
    if (status) return fail();
    if (transfer(1, input, length, 1)) return fail();
    free(input);
    return 0;
}
