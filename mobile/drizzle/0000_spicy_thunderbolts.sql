CREATE TABLE `devices` (
	`token_hash` text PRIMARY KEY NOT NULL,
	`code` text NOT NULL,
	`user_id` text,
	`expires` integer NOT NULL,
	`created` integer NOT NULL,
	`name` text DEFAULT 'PC' NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `devices_code` ON `devices` (`code`);--> statement-breakpoint
CREATE INDEX `devices_user` ON `devices` (`user_id`);--> statement-breakpoint
CREATE TABLE `friendships` (
	`user_low` text NOT NULL,
	`user_high` text NOT NULL,
	`requester` text NOT NULL,
	`status` text NOT NULL,
	`created` integer NOT NULL,
	PRIMARY KEY(`user_low`, `user_high`)
);
--> statement-breakpoint
CREATE INDEX `friends_high` ON `friendships` (`user_high`);--> statement-breakpoint
CREATE TABLE `profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`handle` text,
	`display` text DEFAULT '' NOT NULL,
	`share` integer DEFAULT 0 NOT NULL,
	`updated` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `profiles_handle` ON `profiles` (`handle`);--> statement-breakpoint
CREATE TABLE `rate_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`count` integer NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `shelves` (
	`user_id` text PRIMARY KEY NOT NULL,
	`songs` text NOT NULL,
	`revision` integer DEFAULT 1 NOT NULL,
	`updated` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `vaults` (
	`user_id` text NOT NULL,
	`vault` text NOT NULL,
	`envelope` text NOT NULL,
	`revision` integer DEFAULT 1 NOT NULL,
	`updated` integer NOT NULL,
	PRIMARY KEY(`user_id`, `vault`)
);
