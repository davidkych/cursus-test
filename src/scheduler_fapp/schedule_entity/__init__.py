import azure.durable_functions as df

def entity(ctx: df.DurableEntityContext):    # noqa: D401
    op    = ctx.operation_name
    state = ctx.get_state(lambda: {})        # {instanceId: {...}}

    if op == "add":
        info = ctx.get_input()
        state[info["instanceId"]] = info

    elif op == "remove":
        instance_id = ctx.get_input()
        state.pop(instance_id, None)

    elif op == "list":
        # For future browse panel
        ctx.set_result(state)

    ctx.set_state(state)

main = df.Entity.create(entity)
