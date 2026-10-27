# Manual de uso de Pick-to-Light

Este manual explica cómo utilizar **Odoo Inventario** con los tags luminosos Pick-to-Light. Está pensado para alumnado de FP Básica y se puede seguir paso a paso.

> Para instalar, configurar o reparar el sistema, consulta el [manual de administración](admin.md).

## 1. ¿Qué hace el sistema?

Cada producto del almacén tiene asociado un **tag**. El tag muestra:

- El nombre del producto.
- El stock disponible.
- La cantidad que hay que colocar o recoger.
- Una luz de color que indica el tipo de trabajo.

Odoo envía la tarea al tag. Cuando terminas el trabajo físico, confirmas la operación en el tag y Odoo actualiza el inventario.

## 2. Conocer el tag

El tag tiene una pantalla, un LED RGB y tres botones físicos:

![Partes del tag Pick-to-Light](images/15-esquema-botones-tag-real.png)

La pantalla de trabajo solo necesita mostrar:

- **Producto**: artículo que debes mover.
- **Stock**: unidades registradas en Odoo.
- **Cantidad pendiente**: unidades que debes colocar o recoger.

### Colores importantes

| Color del LED | Significado | Qué debes hacer |
|---|---|---|
| Azul | Recepción o entrada | Colocar mercancía en el almacén. |
| Verde | Entrega o salida | Recoger mercancía del almacén. |
| Apagado | No hay tarea pendiente | No mover mercancía. |

> Los nombres de los botones físicos y los números que recibe Odoo pueden ser diferentes. Utiliza únicamente el botón de confirmación que haya indicado el profesor o responsable del equipo.

## 3. Antes de empezar

Comprueba lo siguiente:

- Tienes abierta la aplicación **Inventario** de Odoo.
- El producto de la operación coincide con el producto mostrado en el tag.
- El número de unidades es correcto.
- La luz tiene el color esperado.
- No hay otra persona trabajando con el mismo tag.

La dirección de acceso en el equipo del aula es:

```text
http://localhost:8069/odoo/inventory
```

Si Odoo pide usuario y contraseña, utiliza los datos entregados por el profesor.

## 4. Consultar productos

1. Entra en **Inventario**.
2. Abre el menú **Productos**.
3. Pulsa **Productos**.
4. Busca el artículo por su nombre.
5. Comprueba la cantidad **A la mano**.

![Listado de productos](images/02-productos-listado.png)

### Ver qué tag tiene un producto

Normalmente la MAC la configura el profesor o administrador. Para consultarla:

1. Abre la ficha del producto.
2. Entra en la pestaña **Inventario**.
3. Busca el apartado **Picksmart PTL Integration**.
4. El campo **Tag MAC Address** identifica el tag del producto.

![MAC del tag en la ficha del producto](images/03-producto-picksmart.png)

> No cambies la MAC ni **Pickup Quantity** salvo que el profesor te lo indique. Una MAC incorrecta enviará la tarea a otro tag o impedirá que funcione.

## 5. Realizar una recepción

Una recepción significa que llega mercancía y hay que **colocarla en el almacén**.

### En Odoo

1. Abre **Inventario → Operaciones → Recepciones**.
2. Abre la recepción indicada por el profesor.
3. Comprueba el producto y la cantidad.
4. Pulsa **Validar** para enviar la tarea al tag.

![Detalle de una recepción](images/05-recepcion-detalle.png)

### En el almacén

1. Busca el tag con el nombre del producto.
2. Comprueba que el LED está **azul**.
3. Lee la **cantidad pendiente**. En las recepciones aparece con signo negativo; por ejemplo, `-10` significa colocar 10 unidades.
4. Cuenta y coloca las unidades.
5. Vuelve a contarlas antes de confirmar.
6. Pulsa una sola vez el botón de confirmación indicado por el profesor.
7. Comprueba que la cantidad queda a cero y que el LED se apaga.

![Tag durante una recepción](images/13-mockup-tag-recepcion-real.png)

**Ejemplo:** si el tag muestra `-12`, debes colocar 12 unidades. El signo menos indica entrada; no significa que el stock sea negativo.

## 6. Realizar una entrega

Una entrega significa que la mercancía sale y hay que **recogerla del almacén**.

### En Odoo

1. Abre **Inventario → Operaciones → Entregas**.
2. Abre la entrega indicada.
3. Comprueba el producto, la disponibilidad y la cantidad.
4. Pulsa **Validar** para enviar la tarea al tag.

![Detalle de una entrega](images/07-entrega-detalle.png)

### En el almacén

1. Busca el tag con el nombre del producto.
2. Comprueba que el LED está **verde**.
3. Lee la cantidad pendiente.
4. Cuenta y retira esa cantidad.
5. Vuelve a contar antes de confirmar.
6. Pulsa una sola vez el botón de confirmación indicado por el profesor.
7. Comprueba que la cantidad queda a cero y que el LED se apaga.

![Tag durante una entrega](images/14-mockup-tag-entrega-real.png)

**Ejemplo:** si el tag muestra `5`, debes recoger 5 unidades del producto indicado.

## 7. Trabajar con un traslado por lote

Un lote reúne varias operaciones para trabajar de forma más rápida. Puede contener **varios productos diferentes**.

Odoo hace lo siguiente:

1. Reúne los movimientos del lote.
2. Suma por separado las cantidades de cada producto.
3. Envía el total de cada producto a su tag.

![Un lote con varios productos y tags](images/16-mockup-lote-varios-productos.png)

Cada producto debe tener su propia MAC y su propio tag:

```text
Camisa hombre  → Tag de camisa hombre  → Cantidad total de camisa hombre
Camisa mujer   → Tag de camisa mujer   → Cantidad total de camisa mujer
Complementos   → Tag de complementos   → Cantidad total de complementos
```

### Pasos para trabajar con el lote

1. Abre **Inventario → Operaciones → Traslados por lote**.
2. Abre el lote indicado.
3. Revisa la lista completa de productos.
4. Pulsa **Validar** para enviar las cantidades a los tags.
5. Ve al almacén y localiza todos los tags encendidos.
6. Trabaja producto por producto; no mezcles las unidades.
7. Cuenta la cantidad del primer producto y confirma su tag.
8. Continúa con los demás productos hasta que todos los tags queden apagados.
9. Vuelve a Odoo y comprueba el estado del lote.

![Detalle de un traslado por lote](images/09-traslado-lote-detalle.png)

> Confirmar un tag solo confirma el producto asociado a ese tag. No significa que hayas terminado todos los productos del lote.

## 8. Normas para evitar errores

- Lee siempre el nombre del producto antes de mover unidades.
- Cuenta dos veces antes de confirmar.
- No pulses el botón varias veces.
- No utilices los botones de ajuste de stock sin permiso.
- No cambies la MAC del producto.
- No confirmes una tarea realizada por otra persona.
- Si el color, el producto o la cantidad no coinciden, detente y avisa al profesor.

## 9. ¿Qué hago si algo falla?

### El tag no se enciende

1. No realices el movimiento todavía.
2. Comprueba que has validado la operación correcta.
3. Avisa al profesor o responsable.

### El producto del tag no coincide

No muevas mercancía y no pulses ningún botón. Puede existir un error en la MAC asociada.

### La cantidad no coincide con Odoo

No elijas una cantidad por tu cuenta. Detén la operación y avisa al profesor.

### He contado mal después de confirmar

No intentes arreglarlo pulsando otros botones. Anota el producto y la diferencia, y comunícalo inmediatamente.

### El LED sigue encendido después de confirmar

Espera unos segundos y no vuelvas a pulsar. Si continúa encendido, avisa al responsable.

## 10. Resumen rápido

### Recepción

```text
LED azul → leer producto → colocar unidades → contar → confirmar
```

### Entrega

```text
LED verde → leer producto → recoger unidades → contar → confirmar
```

### Lote

```text
varios productos → un tag por producto → trabajar uno a uno → confirmar todos
```

## 11. Lista de comprobación final

Antes de terminar, responde:

- [ ] ¿He trabajado con el producto correcto?
- [ ] ¿He movido la cantidad correcta?
- [ ] ¿He confirmado una sola vez?
- [ ] ¿La cantidad pendiente ha quedado a cero?
- [ ] ¿El LED se ha apagado?
- [ ] Si era un lote, ¿he terminado todos los productos?

Si todas las respuestas son afirmativas, la operación está terminada.

---

[Manual técnico y de administración →](admin.md)
