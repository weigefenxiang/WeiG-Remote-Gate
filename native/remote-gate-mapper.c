#define _GNU_SOURCE

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <net/if.h>
#include <netdb.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef SO_BINDTODEVICE
#define SO_BINDTODEVICE 25
#endif

#define STUN_COOKIE 0x2112A442u
#define STUN_BINDING_REQUEST 0x0001u
#define STUN_BINDING_SUCCESS 0x0101u
#define STUN_ATTR_MAPPED_ADDRESS 0x0001u
#define STUN_ATTR_XOR_MAPPED_ADDRESS 0x0020u
#define MAX_PACKET 65535
#define MAX_SESSIONS_LIMIT 256

struct config {
    char device[IFNAMSIZ];
    char service_id[96];
    uint16_t service_port;
    char status_file[512];
    char go_file[512];
    char stun_host[256];
    char stun_address[INET_ADDRSTRLEN];
    uint16_t stun_port;
    int keepalive;
    int idle_timeout;
    int max_sessions;
};

struct session {
    int fd;
    int used;
    struct sockaddr_in peer;
    time_t last_activity;
};

static volatile sig_atomic_t g_stop = 0;

static void on_signal(int signo) {
    (void)signo;
    g_stop = 1;
}

static uint16_t read_u16(const unsigned char *p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static uint32_t read_u32(const unsigned char *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static void write_u16(unsigned char *p, uint16_t value) {
    p[0] = (unsigned char)(value >> 8);
    p[1] = (unsigned char)(value & 0xffu);
}

static void write_u32(unsigned char *p, uint32_t value) {
    p[0] = (unsigned char)(value >> 24);
    p[1] = (unsigned char)((value >> 16) & 0xffu);
    p[2] = (unsigned char)((value >> 8) & 0xffu);
    p[3] = (unsigned char)(value & 0xffu);
}

static int safe_name(const char *value) {
    size_t i;
    if (!value || !*value) return 0;
    for (i = 0; value[i]; ++i) {
        unsigned char c = (unsigned char)value[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.' ||
            c == ':' || c == '@' || c == '+') {
            continue;
        }
        return 0;
    }
    return 1;
}

static int safe_host(const char *value) {
    size_t i;
    if (!value || !*value) return 0;
    for (i = 0; value[i]; ++i) {
        unsigned char c = (unsigned char)value[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '.') {
            continue;
        }
        return 0;
    }
    return 1;
}

static int parse_int(const char *text, int minimum, int maximum, int *out) {
    char *end = NULL;
    long value;
    if (!text || !*text) return -1;
    errno = 0;
    value = strtol(text, &end, 10);
    if (errno || !end || *end || value < minimum || value > maximum) return -1;
    *out = (int)value;
    return 0;
}

static void usage(const char *argv0) {
    fprintf(stderr,
        "usage: %s --device DEV --service-id ID --service-port PORT "
        "--status-file PATH --go-file PATH --stun-host HOST --stun-port PORT "
        "[--keepalive SEC] [--idle-timeout SEC] [--max-sessions N]\n",
        argv0);
}

static int parse_args(int argc, char **argv, struct config *cfg) {
    int i;
    int value;
    memset(cfg, 0, sizeof(*cfg));
    cfg->stun_port = 3478;
    cfg->keepalive = 20;
    cfg->idle_timeout = 180;
    cfg->max_sessions = 64;

    for (i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        const char *next = (i + 1 < argc) ? argv[i + 1] : NULL;
        if (!strcmp(arg, "--device") && next) {
            snprintf(cfg->device, sizeof(cfg->device), "%s", next); ++i;
        } else if (!strcmp(arg, "--service-id") && next) {
            snprintf(cfg->service_id, sizeof(cfg->service_id), "%s", next); ++i;
        } else if (!strcmp(arg, "--service-port") && next) {
            if (parse_int(next, 1, 65535, &value)) return -1;
            cfg->service_port = (uint16_t)value; ++i;
        } else if (!strcmp(arg, "--status-file") && next) {
            snprintf(cfg->status_file, sizeof(cfg->status_file), "%s", next); ++i;
        } else if (!strcmp(arg, "--go-file") && next) {
            snprintf(cfg->go_file, sizeof(cfg->go_file), "%s", next); ++i;
        } else if (!strcmp(arg, "--stun-host") && next) {
            snprintf(cfg->stun_host, sizeof(cfg->stun_host), "%s", next); ++i;
        } else if (!strcmp(arg, "--stun-port") && next) {
            if (parse_int(next, 1, 65535, &value)) return -1;
            cfg->stun_port = (uint16_t)value; ++i;
        } else if (!strcmp(arg, "--keepalive") && next) {
            if (parse_int(next, 5, 120, &cfg->keepalive)) return -1;
            ++i;
        } else if (!strcmp(arg, "--idle-timeout") && next) {
            if (parse_int(next, 30, 3600, &cfg->idle_timeout)) return -1;
            ++i;
        } else if (!strcmp(arg, "--max-sessions") && next) {
            if (parse_int(next, 1, MAX_SESSIONS_LIMIT, &cfg->max_sessions)) return -1;
            ++i;
        } else {
            return -1;
        }
    }

    if (!safe_name(cfg->device) || !safe_name(cfg->service_id) || !cfg->service_port ||
        !cfg->status_file[0] || !cfg->go_file[0] || !safe_host(cfg->stun_host) || !cfg->stun_port) {
        return -1;
    }
    return 0;
}

static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static int fill_random(unsigned char *out, size_t length) {
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    size_t done = 0;
    if (fd >= 0) {
        while (done < length) {
            ssize_t n = read(fd, out + done, length - done);
            if (n > 0) done += (size_t)n;
            else if (n < 0 && errno == EINTR) continue;
            else break;
        }
        close(fd);
    }
    if (done == length) return 0;
    srand((unsigned int)(time(NULL) ^ getpid()));
    while (done < length) out[done++] = (unsigned char)(rand() & 0xff);
    return 0;
}

static int write_status(
    const struct config *cfg,
    const char *state,
    uint16_t ingress_port,
    const char *external_address,
    uint16_t external_port,
    time_t observed_at
) {
    char tmp[640];
    FILE *fp;
    int fd;
    snprintf(tmp, sizeof(tmp), "%s.tmp.%ld", cfg->status_file, (long)getpid());
    fp = fopen(tmp, "w");
    if (!fp) return -1;
    fd = fileno(fp);
    if (fprintf(fp,
        "{\"state\":\"%s\",\"device\":\"%s\",\"service_id\":\"%s\","
        "\"ingress_port\":%u,\"external_address\":\"%s\",\"external_port\":%u,"
        "\"stun_address\":\"%s\",\"stun_port\":%u,\"observed_at\":%ld,\"pid\":%ld}\n",
        state, cfg->device, cfg->service_id, (unsigned)ingress_port,
        external_address ? external_address : "", (unsigned)external_port,
        cfg->stun_address, (unsigned)cfg->stun_port,
        (long)observed_at, (long)getpid()) < 0) {
        fclose(fp); unlink(tmp); return -1;
    }
    if (fflush(fp) != 0 || fsync(fd) != 0) {
        fclose(fp); unlink(tmp); return -1;
    }
    if (fchmod(fd, 0600) != 0) {
        fclose(fp); unlink(tmp); return -1;
    }
    if (fclose(fp) != 0) {
        unlink(tmp); return -1;
    }
    if (rename(tmp, cfg->status_file) != 0) {
        unlink(tmp); return -1;
    }
    return 0;
}

static int create_mapping_socket(const struct config *cfg, uint16_t *port_out) {
    int fd;
    struct sockaddr_in local;
    socklen_t length = sizeof(local);
    socklen_t device_length = (socklen_t)(strlen(cfg->device) + 1u);

    if (if_nametoindex(cfg->device) == 0) return -1;
    fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, cfg->device, device_length) != 0) {
        close(fd); return -1;
    }
    memset(&local, 0, sizeof(local));
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    local.sin_port = htons(0);
    if (bind(fd, (struct sockaddr *)&local, sizeof(local)) != 0) {
        close(fd); return -1;
    }
    if (getsockname(fd, (struct sockaddr *)&local, &length) != 0) {
        close(fd); return -1;
    }
    if (set_nonblocking(fd) != 0) {
        close(fd); return -1;
    }
    *port_out = ntohs(local.sin_port);
    return fd;
}

static int resolve_stun(struct config *cfg, struct sockaddr_in *out) {
    struct addrinfo hints;
    struct addrinfo *result = NULL;
    struct addrinfo *it;
    char port[16];
    int rc;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    snprintf(port, sizeof(port), "%u", (unsigned)cfg->stun_port);
    rc = getaddrinfo(cfg->stun_host, port, &hints, &result);
    if (rc != 0) return -1;
    for (it = result; it; it = it->ai_next) {
        if (it->ai_family == AF_INET && it->ai_addrlen >= sizeof(struct sockaddr_in)) {
            memcpy(out, it->ai_addr, sizeof(*out));
            if (!inet_ntop(AF_INET, &out->sin_addr, cfg->stun_address, sizeof(cfg->stun_address))) {
                freeaddrinfo(result);
                return -1;
            }
            freeaddrinfo(result);
            return 0;
        }
    }
    freeaddrinfo(result);
    return -1;
}

static int send_stun_request(
    int fd,
    const struct sockaddr_in *server,
    unsigned char transaction[12]
) {
    unsigned char packet[20];
    fill_random(transaction, 12);
    memset(packet, 0, sizeof(packet));
    write_u16(packet, STUN_BINDING_REQUEST);
    write_u16(packet + 2, 0);
    write_u32(packet + 4, STUN_COOKIE);
    memcpy(packet + 8, transaction, 12);
    return sendto(fd, packet, sizeof(packet), 0, (const struct sockaddr *)server, sizeof(*server)) == (ssize_t)sizeof(packet) ? 0 : -1;
}

static int parse_stun_mapping(
    const unsigned char *packet,
    size_t length,
    const unsigned char transaction[12],
    struct in_addr *address,
    uint16_t *port
) {
    size_t offset;
    uint16_t message_length;
    if (length < 20 || read_u16(packet) != STUN_BINDING_SUCCESS || read_u32(packet + 4) != STUN_COOKIE) return -1;
    if (memcmp(packet + 8, transaction, 12) != 0) return -1;
    message_length = read_u16(packet + 2);
    if ((size_t)message_length + 20 > length) return -1;

    offset = 20;
    while (offset + 4 <= 20u + message_length) {
        uint16_t type = read_u16(packet + offset);
        uint16_t attr_len = read_u16(packet + offset + 2);
        const unsigned char *value = packet + offset + 4;
        size_t padded = (size_t)((attr_len + 3u) & ~3u);
        if (offset + 4u + padded > length) return -1;
        if ((type == STUN_ATTR_XOR_MAPPED_ADDRESS || type == STUN_ATTR_MAPPED_ADDRESS) && attr_len >= 8 && value[1] == 0x01) {
            uint16_t mapped_port = read_u16(value + 2);
            uint32_t mapped_addr = read_u32(value + 4);
            if (type == STUN_ATTR_XOR_MAPPED_ADDRESS) {
                mapped_port ^= (uint16_t)(STUN_COOKIE >> 16);
                mapped_addr ^= STUN_COOKIE;
            }
            address->s_addr = htonl(mapped_addr);
            *port = mapped_port;
            return 0;
        }
        offset += 4u + padded;
    }
    return -1;
}

static int sockaddr_equal(const struct sockaddr_in *a, const struct sockaddr_in *b) {
    return a->sin_family == b->sin_family && a->sin_port == b->sin_port && a->sin_addr.s_addr == b->sin_addr.s_addr;
}

static int find_session(struct session *sessions, int count, const struct sockaddr_in *peer) {
    int i;
    for (i = 0; i < count; ++i) {
        if (sessions[i].used && sockaddr_equal(&sessions[i].peer, peer)) return i;
    }
    return -1;
}

static void close_session(struct session *session) {
    if (session->used && session->fd >= 0) close(session->fd);
    memset(session, 0, sizeof(*session));
    session->fd = -1;
}

static int create_session(struct session *sessions, int count, const struct sockaddr_in *peer, uint16_t service_port) {
    int i;
    int fd;
    struct sockaddr_in target;
    for (i = 0; i < count; ++i) if (!sessions[i].used) break;
    if (i == count) return -1;

    fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    memset(&target, 0, sizeof(target));
    target.sin_family = AF_INET;
    target.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    target.sin_port = htons(service_port);
    if (connect(fd, (struct sockaddr *)&target, sizeof(target)) != 0 || set_nonblocking(fd) != 0) {
        close(fd); return -1;
    }

    sessions[i].fd = fd;
    sessions[i].used = 1;
    sessions[i].peer = *peer;
    sessions[i].last_activity = time(NULL);
    return i;
}

static void expire_sessions(struct session *sessions, int count, int idle_timeout) {
    int i;
    time_t now = time(NULL);
    for (i = 0; i < count; ++i) {
        if (sessions[i].used && now - sessions[i].last_activity >= idle_timeout) close_session(&sessions[i]);
    }
}

static int wait_for_go(const struct config *cfg, uint16_t ingress_port) {
    while (!g_stop) {
        if (access(cfg->go_file, F_OK) == 0) return 0;
        if (write_status(cfg, "prepared", ingress_port, "", 0, 0) != 0) return -1;
        sleep(1);
    }
    return -1;
}

static int discover_initial_mapping(
    const struct config *cfg,
    int mapping_fd,
    uint16_t ingress_port,
    const struct sockaddr_in *stun_server,
    struct in_addr *external_addr,
    uint16_t *external_port,
    unsigned char transaction[12]
) {
    unsigned char packet[2048];
    int attempt;
    for (attempt = 0; attempt < 5 && !g_stop; ++attempt) {
        struct pollfd pfd;
        if (send_stun_request(mapping_fd, stun_server, transaction) != 0) continue;
        pfd.fd = mapping_fd; pfd.events = POLLIN; pfd.revents = 0;
        if (poll(&pfd, 1, 2500) > 0 && (pfd.revents & POLLIN)) {
            for (;;) {
                struct sockaddr_in source;
                socklen_t slen = sizeof(source);
                ssize_t n = recvfrom(mapping_fd, packet, sizeof(packet), 0, (struct sockaddr *)&source, &slen);
                if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;
                if (!sockaddr_equal(&source, stun_server)) continue;
                if (parse_stun_mapping(packet, (size_t)n, transaction, external_addr, external_port) == 0) return 0;
            }
        }
        write_status(cfg, "prepared", ingress_port, "", 0, 0);
    }
    return -1;
}

static int run_active(
    const struct config *cfg,
    int mapping_fd,
    uint16_t ingress_port,
    const struct sockaddr_in *stun_server,
    struct in_addr external_addr,
    uint16_t external_port
) {
    struct session *sessions;
    struct pollfd *pfds;
    int *session_index;
    unsigned char packet[MAX_PACKET];
    unsigned char transaction[12];
    time_t last_stun = 0;
    int stun_pending = 0;
    int missed_stun = 0;
    char external_text[INET_ADDRSTRLEN];

    sessions = calloc((size_t)cfg->max_sessions, sizeof(*sessions));
    pfds = calloc((size_t)cfg->max_sessions + 1u, sizeof(*pfds));
    session_index = calloc((size_t)cfg->max_sessions + 1u, sizeof(*session_index));
    if (!sessions || !pfds || !session_index) {
        free(sessions); free(pfds); free(session_index); return -1;
    }
    for (int i = 0; i < cfg->max_sessions; ++i) sessions[i].fd = -1;
    if (!inet_ntop(AF_INET, &external_addr, external_text, sizeof(external_text))) {
        free(sessions); free(pfds); free(session_index); return -1;
    }
    write_status(cfg, "active", ingress_port, external_text, external_port, time(NULL));

    while (!g_stop) {
        int nfds = 1;
        int rc;
        time_t now = time(NULL);
        pfds[0].fd = mapping_fd; pfds[0].events = POLLIN; pfds[0].revents = 0; session_index[0] = -1;
        for (int i = 0; i < cfg->max_sessions; ++i) {
            if (!sessions[i].used) continue;
            pfds[nfds].fd = sessions[i].fd;
            pfds[nfds].events = POLLIN;
            pfds[nfds].revents = 0;
            session_index[nfds] = i;
            ++nfds;
        }

        if (now - last_stun >= cfg->keepalive) {
            if (stun_pending) ++missed_stun;
            if (send_stun_request(mapping_fd, stun_server, transaction) == 0) {
                stun_pending = 1;
                last_stun = now;
            }
            if (missed_stun >= 4) {
                for (int i = 0; i < cfg->max_sessions; ++i) close_session(&sessions[i]);
                free(sessions); free(pfds); free(session_index); return -1;
            }
        }

        rc = poll(pfds, (nfds_t)nfds, 1000);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) break;

        if (pfds[0].revents & POLLIN) {
            for (;;) {
                struct sockaddr_in source;
                socklen_t slen = sizeof(source);
                ssize_t n = recvfrom(mapping_fd, packet, sizeof(packet), 0, (struct sockaddr *)&source, &slen);
                if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;

                if (sockaddr_equal(&source, stun_server)) {
                    struct in_addr new_addr;
                    uint16_t new_port;
                    if (stun_pending && parse_stun_mapping(packet, (size_t)n, transaction, &new_addr, &new_port) == 0) {
                        stun_pending = 0;
                        missed_stun = 0;
                        if (new_addr.s_addr != external_addr.s_addr || new_port != external_port) {
                            external_addr = new_addr;
                            external_port = new_port;
                        }
                        if (inet_ntop(AF_INET, &external_addr, external_text, sizeof(external_text))) {
                            write_status(cfg, "active", ingress_port, external_text, external_port, time(NULL));
                        }
                    }
                    continue;
                }

                int index = find_session(sessions, cfg->max_sessions, &source);
                if (index < 0) index = create_session(sessions, cfg->max_sessions, &source, cfg->service_port);
                if (index < 0) continue;
                if (send(sessions[index].fd, packet, (size_t)n, 0) >= 0) sessions[index].last_activity = time(NULL);
            }
        }

        for (int p = 1; p < nfds; ++p) {
            int index = session_index[p];
            if (index < 0 || !sessions[index].used || !(pfds[p].revents & POLLIN)) continue;
            for (;;) {
                ssize_t n = recv(sessions[index].fd, packet, sizeof(packet), 0);
                if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) break;
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) break;
                if (sendto(mapping_fd, packet, (size_t)n, 0,
                           (struct sockaddr *)&sessions[index].peer, sizeof(sessions[index].peer)) >= 0) {
                    sessions[index].last_activity = time(NULL);
                }
            }
        }
        expire_sessions(sessions, cfg->max_sessions, cfg->idle_timeout);
    }

    for (int i = 0; i < cfg->max_sessions; ++i) close_session(&sessions[i]);
    free(sessions); free(pfds); free(session_index);
    return g_stop ? 0 : -1;
}

int main(int argc, char **argv) {
    struct config cfg;
    int mapping_fd = -1;
    uint16_t ingress_port = 0;
    struct sockaddr_in stun_server;
    struct in_addr external_addr;
    uint16_t external_port = 0;
    unsigned char transaction[12];
    char external_text[INET_ADDRSTRLEN];
    int rc = 1;

    if (parse_args(argc, argv, &cfg) != 0) {
        usage(argv[0]);
        return 2;
    }

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGHUP, on_signal);
    umask(077);

    if (resolve_stun(&cfg, &stun_server) != 0) {
        write_status(&cfg, "failed", 0, "", 0, 0);
        return 1;
    }
    mapping_fd = create_mapping_socket(&cfg, &ingress_port);
    if (mapping_fd < 0) {
        write_status(&cfg, "failed", 0, "", 0, 0);
        return 1;
    }
    if (write_status(&cfg, "prepared", ingress_port, "", 0, 0) != 0) goto out;
    if (wait_for_go(&cfg, ingress_port) != 0) goto out;
    if (discover_initial_mapping(&cfg, mapping_fd, ingress_port, &stun_server, &external_addr, &external_port, transaction) != 0) {
        write_status(&cfg, "failed", ingress_port, "", 0, 0);
        goto out;
    }
    if (!inet_ntop(AF_INET, &external_addr, external_text, sizeof(external_text))) {
        write_status(&cfg, "failed", ingress_port, "", 0, 0);
        goto out;
    }
    if (write_status(&cfg, "active", ingress_port, external_text, external_port, time(NULL)) != 0) goto out;
    rc = run_active(&cfg, mapping_fd, ingress_port, &stun_server, external_addr, external_port) == 0 ? 0 : 1;
    if (rc != 0 && !g_stop) write_status(&cfg, "failed", ingress_port, "", 0, 0);

out:
    if (mapping_fd >= 0) close(mapping_fd);
    return rc;
}
