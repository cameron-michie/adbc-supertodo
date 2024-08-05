<script lang="ts">
	import { onMount } from "svelte";
	import * as Ably from "ably";

	const channelName = "todos";

	let client = new Ably.Realtime({
		key: import.meta.env.VITE_ABLY_API_KEY,
		environment: import.meta.env.VITE_ABLY_ENVIRONMENT ? import.meta.env.VITE_ABLY_ENVIRONMENT : undefined,
	});
    console.log("Connected");
	let channel: Ably.RealtimeChannel;

	interface todo {
		id?: number;
		task: string;
		completed: boolean;
		username: string;
	}

	let username: string;
	let todos: Array<todo> = [];
	let newTask = "";

	const getRandomUsername = async () => {
		let response = await fetch("https://randomuser.me/api/");
		let name = (await response.json()).results[0].name;
		return `${name.first}`;
	};

	const getTodos = async () => {
		var response = await fetch(
			`http://localhost:8000/api/todos?username=${username}`,
			{
				cache: "no-cache",
				headers: {
					"Content-Type": "application/json",
				},
			}
		);
		var result = await response.json();
		if (!result) {
			return [];
		}
        console.log("[result] ", result);
		return result;
	};

	const getInitialTodos = async () => {
		let response = await fetch(`http://localhost:8000/api/todos/initial`, {
			headers: {
				"Content-Type": "application/json",
			},
		});
		return response.json();
	};

	async function resubscribe() {
		if (channel) {
			await channel.unsubscribe();
			await channel.detach();
		}

		// Preserve the initial state by only appending or modifying existing todos
		const userTodos = await getTodos();
		const userTodoIds = userTodos.map(todo => todo.id);
		todos = todos.filter(todo => !userTodoIds.includes(todo.id)).concat(userTodos);

		console.log('[resubscribe] ' + channelName + ' with filter: ' + `headers.username == \`"${username}"\``);
		channel = client.channels.get(channelName);
		await channel.attach();

		channel.subscribe((message) => {
			console.log("[subscribe] message", message);
			if (message.name === "update") {
				todos = todos.map((todo) => {
					if (todo.id === message.data.id) {
						return message.data;
					}
					return todo;
				});
			} else if (message.name === "delete") {
				console.log("[Delete] Deleting ", message.data.task);
				todos = todos.filter((todo) => todo.id !== message.data.id);
			} else if (message.name === "create") {
				todos = [...todos, message.data];
			} else {
				console.warn("unsupported message ", message.name);
			}
			console.log("[subscribe] todos", todos);
		});
	}


	onMount(async function () {
		username = await getRandomUsername();
		todos = await getInitialTodos();
		await resubscribe();
		console.log("[onMount] todos", todos);
	});

	async function addToList() {
		await fetch("http://localhost:8000/api/todos", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({ task: newTask, completed: false, username }),
		});
		newTask = "";
	}

	async function update(index: number) {
		await fetch("http://localhost:8000/api/todos", {
			method: "PUT",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify(todos[index]),
		});
	}

	async function removeFromList(index: number) {
		await fetch(`http://localhost:8000/api/todos?id=${todos[index].id}`, {
			method: "DELETE",
			mode: "cors",
		});
	}
</script>

<input
	bind:value={username}
	type="text"
	placeholder="username..."
	on:change={resubscribe}
/>
<br />
{#if username}
	<input bind:value={newTask} type="text" placeholder="new todo item..." />
	<button on:click={addToList}>Add</button>

	<br />
	{#each todos as item, index}
		<input
			bind:checked={item.completed}
			on:change={() => update(index)}
			type="checkbox"
		/>
		<span class:checked={item.completed}>{item.task}</span>
		<span>@{item.username}</span>
		<button type="button" on:click={() => removeFromList(index)} aria-label="Remove item">❌</button>
		<br />
	{/each}
{/if}

<style>
	.checked {
		text-decoration: line-through;
	}
</style>