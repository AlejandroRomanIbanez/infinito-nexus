ARG AKAUNTING_BASE_IMAGE
ARG AKAUNTING_BASE_VERSION

FROM ${AKAUNTING_BASE_IMAGE}:${AKAUNTING_BASE_VERSION}

RUN rm -rf /var/lib/apt/lists/* \
 && apt-get -o Acquire::Retries=3 update \
 && apt-get -y -o Acquire::Retries=3 upgrade --no-install-recommends \
 && apt-get -o Acquire::Retries=3 install -y \
    build-essential \
    imagemagick \
    libfreetype6-dev \
    libicu-dev \
    libjpeg62-turbo-dev \
    libjpeg-dev \
    libmcrypt-dev \
    libonig-dev \
    libpng-dev \
    libpq-dev \
    libssl-dev \
    libxml2-dev \
    libxrender1 \
    libzip-dev \
    locales \
    openssl \
    unzip \
    zip \
    zlib1g-dev \
    --no-install-recommends \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN sed -i 's/^# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen \
 && locale-gen

# Exception: exif is not in upstream akaunting/docker, but Akaunting 3.3.0
# runs every uploaded logo through Intervention orientate(), which throws
# without it and rejects the upload as "must be an image".
RUN docker-php-ext-configure gd \
    --with-freetype \
    --with-jpeg \
 && docker-php-ext-install -j$(nproc) \
    gd \
    bcmath \
    exif \
    intl \
    mbstring \
    pcntl \
    pdo \
    pdo_mysql \
    zip

RUN mkdir -p /var/www/akaunting \
 && {{ 600 | curl }} -Lo /tmp/akaunting.zip 'https://akaunting.com/download.php?version=latest&utm_source=docker&utm_campaign=developers' \
 && unzip /tmp/akaunting.zip -d /var/www/html \
 && rm -f /tmp/akaunting.zip

COPY files/akaunting.sh /usr/local/bin/akaunting.sh
COPY files/html /var/www/html

ENTRYPOINT ["/usr/local/bin/akaunting.sh"]
CMD ["--start"]
