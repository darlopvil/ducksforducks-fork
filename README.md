# Ducks for Ducks

Un frontend respetuoso con la privacidad para GeeksforGeeks.

Este es un fork de [PrivateCoffee/ducksforducks](https://git.private.coffee/PrivateCoffee/ducksforducks)
con correcciones y funcionalidades añadidas. Ver [Diferencias con upstream](#diferencias-con-upstream).

## Uso

Sustituye `geeksforgeeks.org` por el dominio de tu instancia en la URL de
cualquier artículo:

```
https://www.geeksforgeeks.org/dsa/bubble-sort-algorithm/
https://tu-instancia.example/dsa/bubble-sort-algorithm/
```

Las imágenes se sirven a través de la instancia, de modo que el navegador
nunca contacta con GeeksforGeeks.

## Configuración

| Variable | Por defecto | Descripción |
|---|---|---|
| `PORT` | `8113` | Puerto en el que escucha el servidor de desarrollo |
| `DEBUG` | sin definir | Activa el depurador de Flask. Acepta `1`, `true`, `yes`, `on` |
| `REQUEST_TIMEOUT` | `20` | Tiempo máximo en segundos para las peticiones salientes |
| `MAX_PROXY_BYTES` | `10485760` | Tamaño máximo en bytes al proxear un recurso |

## Despliegue con Docker

```bash
docker compose up -d --build
```

`docker-compose.yml`:

```yaml
services:
  ducksforducks:
    build: .
    container_name: ducksforducks_app
    restart: unless-stopped
    ports:
      - "8113:8113"
```

La imagen sirve la aplicación con gunicorn. `main()` y la variable `PORT`
solo se aplican al arrancar el servidor de desarrollo directamente.

## Ejecución desde el código

```bash
pip install .
ducksforducks
```

O, para desarrollo:

```bash
python -m ducksforducks.app
```

## Diferencias con upstream

- Los bloques de código en varios lenguajes se reconstruyen como pestañas sin
  JavaScript, en lugar de mostrarse apilados
- Resaltado de sintaxis con la paleta Monokai, la misma que usa GeeksforGeeks
- Botones "Copiar" y "Ejecutar en tio.run" en cada bloque de código
- Las páginas de práctica (`/problems/<slug>/<n>`) las sirve la propia
  instancia, con un editor de tio.run empotrado por lenguaje
- Los carruseles de imágenes se recuperan como listas verticales
- Tema oscuro, sobre Bootstrap 5.3
- Tablas y bloques destacados con estilo
- Las rutas que no pueden ser artículos (`/favicon.ico`, `/.env`, sondas de
  escáneres) se rechazan sin llegar a consultar GeeksforGeeks
- Timeouts y límite de tamaño en las peticiones salientes
- Dockerfile

## Limitaciones conocidas

- La portada de GeeksforGeeks y los perfiles de usuario no están
  implementados
- tio.run despliega automáticamente las secciones Header y Footer, por lo que
  el driver del problema queda visible en el editor empotrado
- Las expresiones de complejidad se muestran como texto plano, igual que en
  GeeksforGeeks

## Licencia

MIT. Ver [LICENSE](LICENSE).

Obra original del equipo de [Private.coffee](https://private.coffee).